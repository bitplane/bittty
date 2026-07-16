"""Regression tests for the Tier-0 correctness bugs."""

from bittty.parser import Parser
from bittty.terminal import Terminal


def _term():
    terminal = Terminal(width=20, height=10)
    return terminal, Parser(terminal.board)


def test_origin_mode_makes_cup_relative_to_the_scroll_region():
    terminal, parser = _term()
    parser.feed("\x1b[3;6r")  # DECSTBM: scroll region rows 3..6 (0-based 2..5)
    parser.feed("\x1b[?6h")  # DECOM on

    parser.feed("\x1b[1;1H")  # CUP to region-relative home
    assert (terminal.board.cursor.x, terminal.board.cursor.y) == (0, 2)  # top of region

    parser.feed("\x1b[99;1H")  # row far past the region -> clamped to region bottom
    assert terminal.board.cursor.y == 5

    # Without origin mode, CUP is absolute again.
    parser.feed("\x1b[?6l")
    parser.feed("\x1b[1;1H")
    assert (terminal.board.cursor.x, terminal.board.cursor.y) == (0, 0)


def test_decaln_fills_the_screen_and_does_not_leak_an_eight():
    terminal, parser = _term()
    parser.feed("\x1b#8")
    assert terminal.board.screen.current_buffer.get_line_text(0) == "E" * 20  # filled, not a stray "8"
    assert "8" not in terminal.capture_pane()


def test_ansi_set_mode_7_does_not_toggle_autowrap():
    terminal, parser = _term()
    parser.feed("\x1b[?7l")  # DECRST private 7 -> autowrap off (the real control)
    assert terminal.board.modes.auto_wrap is False

    parser.feed("\x1b[7h")  # ANSI SM 7 (no '?') must NOT turn autowrap back on
    assert terminal.board.modes.auto_wrap is False
