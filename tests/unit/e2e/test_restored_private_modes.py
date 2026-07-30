"""Behaviour restored behind DEC/xterm private modes 42, 45/1045, and 95."""

from bittty import Board
from bittty.parser import Parser


def _term(width=5, height=3):
    board = Board(width=width, height=height)
    return board, Parser(board)


def test_decnrcm_gates_national_charset_designation():
    board, parser = _term(width=20)

    parser.feed("\x1b(K@[")
    assert board.charset.g0_charset == "B"
    assert board.blitter.current_buffer.get_line_text(0).startswith("@[")

    parser.feed("\r\x1b[?42h@[")
    assert board.charset.g0_charset == "B"  # an ignored designation is not retroactive
    assert board.blitter.current_buffer.get_line_text(0).startswith("@[")

    parser.feed("\r\x1b(K@[")
    assert board.charset.g0_charset == "K"
    assert board.blitter.current_buffer.get_line_text(0).startswith("§Ä")


def test_decnrcm_does_not_gate_dec_special_graphics():
    board, parser = _term()

    parser.feed("\x1b(0q")

    assert board.blitter.current_buffer.get_line_text(0).startswith("─")


def test_reverse_wrap_only_crosses_an_auto_wrapped_line():
    board, parser = _term()
    parser.feed("\x1b[?45hABCDEf")
    board.cursor.set_position(0, 1)

    parser.feed("\b")

    assert (board.cursor.x, board.cursor.y) == (4, 0)

    board.cursor.set_position(0, 2)
    parser.feed("\b")
    assert (board.cursor.x, board.cursor.y) == (0, 2)


def test_reverse_wrap_requires_autowrap():
    board, parser = _term()
    parser.feed("\x1b[?45h\x1b[?7lABCDE")
    board.cursor.set_position(0, 1)

    parser.feed("\b")

    assert (board.cursor.x, board.cursor.y) == (0, 1)


def test_extended_reverse_wrap_crosses_any_line_and_cycles_at_top():
    board, parser = _term()
    parser.feed("\x1b[?1045h")

    board.cursor.set_position(0, 1)
    parser.feed("\b")
    assert (board.cursor.x, board.cursor.y) == (4, 0)

    board.cursor.set_position(0, 0)
    parser.feed("\b")
    assert (board.cursor.x, board.cursor.y) == (4, 2)


def test_reverse_wrap_cancels_delayed_wrap_before_moving_left():
    board, parser = _term()
    parser.feed("\x1b[?45hABCDE")

    parser.feed("\b")

    assert (board.cursor.display_x, board.cursor.y) == (4, 0)


def test_reverse_wrap_applies_to_cub_counts():
    board, parser = _term()
    parser.feed("\x1b[?1045h")
    board.cursor.set_position(1, 1)

    parser.feed("\x1b[3D")

    assert (board.cursor.x, board.cursor.y) == (3, 0)


def test_reverse_wrap_uses_left_right_margins():
    board, parser = _term(width=8)
    parser.feed("\x1b[?69h\x1b[3;6s\x1b[1;3H\x1b[?45hABCDe")
    board.cursor.set_position(2, 1)

    parser.feed("\b")

    assert (board.cursor.x, board.cursor.y) == (5, 0)


def test_auto_wrap_metadata_moves_with_scrolling_lines():
    board, parser = _term(height=2)
    parser.feed("\x1b[?45hABCDEfghijK")
    board.cursor.set_position(0, 1)

    parser.feed("\b")

    assert (board.cursor.x, board.cursor.y) == (4, 0)


def test_decncsm_preserves_content_during_column_switches():
    board = Board(width=80, height=5)
    parser = Parser(board)
    parser.feed("\x1b[?40h\x1b[?95hhello\x1b[?3h")

    assert board.width == 132
    assert board.blitter.current_buffer.get_line_text(0).startswith("hello")
    assert (board.cursor.x, board.cursor.y) == (0, 0)

    parser.feed("\x1b[?95l\x1b[?3l")
    assert board.width == 80
    assert board.blitter.current_buffer.get_line_text(0).strip() == ""
