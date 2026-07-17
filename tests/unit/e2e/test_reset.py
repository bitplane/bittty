"""Reset behaviour: RIS (hard, ESC c) and DECSTR (soft, CSI ! p)."""

from bittty.parser import Parser
from bittty.style import Style
from bittty import Board


def _terminal():
    terminal = Board(width=20, height=5)
    return terminal, Parser(terminal)


def _dirty(terminal, parser):
    """Put the terminal into a non-default state."""
    parser.feed("\x1b[31m")  # SGR red
    parser.feed("\x1b[?6h")  # DECOM origin mode on
    parser.feed("\x1b[2;4r")  # DECSTBM scroll region (non-full)
    parser.feed("\x1b[3;3H")  # move cursor off home
    parser.feed("Hello")  # some content


def test_ris_restores_defaults_and_clears_screen():
    terminal, parser = _terminal()
    _dirty(terminal, parser)
    assert (terminal.blitter.scroll_top, terminal.blitter.scroll_bottom) != (0, 4)

    parser.feed("\x1bc")  # RIS

    assert terminal.style.current == Style()
    assert terminal.modes.origin_mode is False
    assert (terminal.blitter.scroll_top, terminal.blitter.scroll_bottom) == (0, 4)
    assert (terminal.cursor.x, terminal.cursor.y) == (0, 0)
    assert "Hello" not in terminal.capture_pane()  # hard reset clears the screen


def test_decstr_soft_reset_preserves_screen():
    terminal, parser = _terminal()
    _dirty(terminal, parser)
    parser.feed("\x1b[4h")  # IRM insert mode on

    parser.feed("\x1b[!p")  # DECSTR

    # Soft-reset subset is restored...
    assert terminal.style.current == Style()
    assert terminal.modes.origin_mode is False
    assert terminal.modes.insert_mode is False
    assert terminal.modes.cursor_visible is True
    assert (terminal.blitter.scroll_top, terminal.blitter.scroll_bottom) == (0, 4)
    # ...but the screen content is left intact.
    assert "Hello" in terminal.capture_pane()
