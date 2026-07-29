"""Streaming extended-grapheme handling under DEC private mode 2027."""

import pytest

from bittty import Board
from bittty.video import WideHead


def clustered_board(*, width=12, height=3):
    board = Board(width=width, height=height)
    board.parser.feed("\x1b[?2027h")
    return board


def cells(board, y=0):
    return [cell[1] for cell in board.blitter.current_buffer.grid[y]]


def snapshot(board):
    return (
        [[(style, str(char), type(char)) for style, char in row] for row in board.get_content()],
        (board.cursor.x, board.cursor.y),
        board.capture_text(),
    )


def test_mode_off_preserves_legacy_codepoint_writes():
    board = Board(width=5, height=1)
    board.parser.feed("e\u0301")

    assert cells(board)[:2] == ["e", "\u0301"]
    assert board.cursor.x == 2


@pytest.mark.parametrize(
    "text, expected_width",
    [
        ("e\u0301", 1),
        ("🧑\u200d🌾", 2),
        ("🇬🇧", 2),
        ("1\ufe0f\u20e3", 2),
        ("☀\ufe0f", 2),
        ("☀\ufe0e", 1),
        ("각", 2),
        ("क्\u0937ि", 2),
        ("\u0600A", 2),
    ],
)
def test_every_codepoint_split_matches_one_shot(text, expected_width):
    whole = clustered_board()
    whole.parser.feed(text)
    expected = snapshot(whole)

    for split in range(1, len(text)):
        streamed = clustered_board()
        streamed.parser.feed(text[:split])
        streamed.parser.feed(text[split:])
        assert snapshot(streamed) == expected

    assert whole.cursor.x == expected_width


def test_cluster_is_stored_once_with_a_structural_wide_marker():
    board = clustered_board()
    board.parser.feed("🧑")
    board.parser.feed("\u200d🌾")

    assert cells(board)[:2] == ["🧑\u200d🌾", ""]
    assert isinstance(cells(board)[0], WideHead)
    assert board.capture_pane().count("🧑\u200d🌾") == 1


def test_safe_style_change_does_not_split_or_restyle_cluster():
    board = clustered_board()
    board.parser.feed("\x1b[31me\x1b[34m\u0301")

    head = board.blitter.current_buffer.get_cell(0, 0)
    assert head[1] == "e\u0301"
    assert head[0].fg.mode == "indexed"
    assert head[0].fg.value == 1


def test_cursor_movement_invalidates_the_streaming_tail():
    board = clustered_board()
    board.parser.feed("e\x1b[C\u0301")

    assert cells(board)[:3] == ["e", " ", " "]
    assert board.cursor.x == 2


def test_orphan_zero_width_mark_is_ignored():
    board = clustered_board()
    board.parser.feed("\u0301A")

    assert cells(board)[:2] == ["A", " "]
    assert board.cursor.x == 1


def test_split_prepend_sequence_waits_for_its_base():
    board = clustered_board()
    board.parser.feed("\u0600")
    assert board.cursor.x == 0
    board.parser.feed("A")

    assert cells(board)[:2] == ["\u0600A", ""]
    assert board.cursor.x == 2


def test_width_growth_in_final_column_relocates_before_wrapping():
    board = clustered_board(width=4, height=2)
    board.cursor.x = 3
    board.parser.feed("☀")
    board.parser.feed("\ufe0f")

    assert cells(board, 0) == [" "] * 4
    assert cells(board, 1)[:2] == ["☀\ufe0f", ""]
    assert (board.cursor.x, board.cursor.y) == (2, 1)


def test_width_growth_without_autowrap_backs_up():
    board = clustered_board(width=4, height=2)
    board.modes.auto_wrap = False
    board.cursor.x = 3
    board.parser.feed("☀")
    board.parser.feed("\ufe0f")

    assert cells(board, 0)[2:] == ["☀\ufe0f", ""]
    assert (board.cursor.x, board.cursor.y) == (3, 0)


def test_width_shrink_releases_continuation_and_cancels_delayed_wrap():
    board = clustered_board(width=4, height=2)
    board.cursor.x = 2
    board.parser.feed("⌚")
    assert board.cursor.x == 4
    board.parser.feed("\ufe0e")

    assert cells(board, 0)[2:] == ["⌚\ufe0e", " "]
    assert board.cursor.x == 3


def test_insert_mode_streaming_matches_one_shot():
    text = "1\ufe0f\u20e3"

    whole = clustered_board(width=8, height=1)
    whole.parser.feed("abcdef")
    whole.cursor.x = 2
    whole.modes.insert_mode = True
    whole.parser.feed(text)

    streamed = clustered_board(width=8, height=1)
    streamed.parser.feed("abcdef")
    streamed.cursor.x = 2
    streamed.modes.insert_mode = True
    for char in text:
        streamed.parser.feed(char)

    assert snapshot(streamed) == snapshot(whole)


@pytest.mark.parametrize("auto_wrap", [False, True])
def test_insert_mode_final_column_growth_restores_speculative_write(auto_wrap):
    def render(parts):
        board = clustered_board(width=6, height=2)
        board.parser.feed("abcdef")
        board.cursor.x = 5
        board.modes.insert_mode = True
        board.modes.auto_wrap = auto_wrap
        for part in parts:
            board.parser.feed(part)
        return snapshot(board)

    assert render(["☀", "\ufe0f"]) == render(["☀\ufe0f"])


@pytest.mark.parametrize("insert_mode", [False, True])
def test_width_shrink_over_content_matches_one_shot(insert_mode):
    def render(parts):
        board = clustered_board(width=8, height=1)
        board.parser.feed("abcdefgh")
        board.cursor.x = 2
        board.modes.insert_mode = insert_mode
        for part in parts:
            board.parser.feed(part)
        return snapshot(board)

    assert render(["⌚", "\ufe0e"]) == render(["⌚\ufe0e"])


def test_rep_repeats_the_complete_cluster():
    board = clustered_board(width=10, height=1)
    board.parser.feed("e\u0301\x1b[3b")

    assert board.capture_text() == "e\u0301" * 4
    assert board.cursor.x == 4


def test_cluster_growth_is_capped_and_next_boundary_recovers():
    board = clustered_board(width=5, height=1)
    board.parser.feed("A")
    for _ in range(300):
        board.parser.feed("\u0301")
    board.parser.feed("B")

    assert len(cells(board)[0]) == 256
    assert cells(board)[1] == "B"
    assert board.cursor.x == 2


def test_mode_change_and_reset_discard_pending_assembly():
    board = clustered_board(width=5, height=1)
    board.parser.feed("e\x1b[?2027l\u0301")
    assert cells(board)[:2] == ["e", "\u0301"]

    board.parser.feed("\x1b[?2027h\u0600\x1b[!pA")
    assert cells(board)[0] == "A"
