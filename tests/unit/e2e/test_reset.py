"""Reset behaviour: RIS (hard, ESC c) and DECSTR (soft, CSI ! p)."""

from bittty.parser import Parser
from bittty.style import Style
from bittty import Board


def _terminal():
    board = Board(width=20, height=5)
    return board, Parser(board)


def _dirty(board, parser):
    """Put the terminal into a non-default state."""
    parser.feed("\x1b[31m")  # SGR red
    parser.feed("\x1b[?6h")  # DECOM origin mode on
    parser.feed("\x1b[2;4r")  # DECSTBM scroll region (non-full)
    parser.feed("\x1b[3;3H")  # move cursor off home
    parser.feed("Hello")  # some content


def test_ris_restores_defaults_and_clears_screen():
    board, parser = _terminal()
    _dirty(board, parser)
    assert (board.blitter.scroll_top, board.blitter.scroll_bottom) != (0, 4)

    parser.feed("\x1bc")  # RIS

    assert board.style.current == Style()
    assert board.modes.origin_mode is False
    assert (board.blitter.scroll_top, board.blitter.scroll_bottom) == (0, 4)
    assert (board.cursor.x, board.cursor.y) == (0, 0)
    assert "Hello" not in board.capture_pane()  # hard reset clears the screen


def test_decstr_soft_reset_preserves_screen():
    board, parser = _terminal()
    _dirty(board, parser)
    parser.feed("\x1b[4h")  # IRM insert mode on

    parser.feed("\x1b[!p")  # DECSTR

    # Soft-reset subset is restored...
    assert board.style.current == Style()
    assert board.modes.origin_mode is False
    assert board.modes.insert_mode is False
    assert board.modes.cursor_visible is True
    assert (board.blitter.scroll_top, board.blitter.scroll_bottom) == (0, 4)
    # ...but the screen content is left intact.
    assert "Hello" in board.capture_pane()
