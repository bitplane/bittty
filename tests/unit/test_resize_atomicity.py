"""Resize and host output share a chunk-boundary transaction."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from bittty import Board
from bittty.connections import MemoryConnection


@pytest.mark.parametrize("direct", [False, True])
def test_output_waits_for_both_pages_and_pty_resize(monkeypatch, direct):
    board = Board(width=8, height=4)
    board.pty = MemoryConnection()
    entered, release, attempted, completed = (Event() for _ in range(4))
    resize_page = board.blitter.primary_page.resize

    def paused_resize(width, height):
        entered.set()  # Board dimensions changed, but pages have not.
        assert release.wait(2)
        resize_page(width, height)

    monkeypatch.setattr(board.blitter.primary_page, "resize", paused_resize)

    def output():
        attempted.set()
        feed = board.parser.feed if direct else board.feed_host_data
        feed("\x1b[6;12HX")
        assert board.pty.resizes == [(6, 12)]
        completed.set()

    with ThreadPoolExecutor(2) as pool:
        resizing = pool.submit(board.resize, 12, 6)
        try:
            assert entered.wait(2)
            writing = pool.submit(output)
            assert attempted.wait(2)
            assert not completed.wait(0.05)
        finally:
            release.set()
        resizing.result(timeout=2)
        writing.result(timeout=2)
    assert board.blitter.primary_page.get_line_text(5).endswith("X")
    assert (board.blitter.alt_page.width, board.blitter.alt_page.height) == (12, 6)


def test_resize_waits_for_entire_output_chunk(monkeypatch):
    board = Board(width=8, height=4)
    entered, release, attempted, completed = (Event() for _ in range(4))
    print_text = board.parser._print_text

    def paused_print(text):
        entered.set()
        assert release.wait(2)
        assert (board.width, board.height) == (8, 4)
        print_text(text)

    monkeypatch.setattr(board.parser, "_print_text", paused_print)

    def resize():
        attempted.set()
        board.display.resize(4, 2)
        completed.set()

    with ThreadPoolExecutor(2) as pool:
        writing = pool.submit(board.feed_host_data, b"abc\r\ndef")
        try:
            assert entered.wait(2)
            resizing = pool.submit(resize)
            assert attempted.wait(2)
            assert not completed.wait(0.05)
        finally:
            release.set()
        writing.result(timeout=2)
        resizing.result(timeout=2)
    assert board.capture_text() == "abc\ndef"


def test_host_resize_inside_feed_is_reentrant():
    board = Board(width=8, height=4)
    board.feed_host_data(b"\x1b[8;6;12t\x1b[6;12HX")
    assert (board.width, board.height) == (12, 6)
    assert board.blitter.current_page.get_line_text(5).endswith("X")


@pytest.mark.parametrize("size", [(0, 4), (8, 0), (-1, 4)])
def test_invalid_resize_leaves_state_unchanged(size):
    board = Board(width=8, height=4)
    with pytest.raises(ValueError, match="positive"):
        board.resize(*size)
    assert (board.width, board.height) == (8, 4)
    assert board.blitter.primary_page.width == 8
