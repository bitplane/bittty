"""linux `setterm` CSI...] directives as board hardware registers, and ESC[8]."""

from bittty.parser import Parser
from bittty.style import Color
from bittty import Board


def _term():
    terminal = Board(width=20, height=3)
    return terminal, Parser(terminal.board)


def test_setterm_updates_board_registers():
    terminal, parser = _term()
    board = terminal.board
    parser.feed("\x1b[10;440]")  # bell frequency
    parser.feed("\x1b[11;200]")  # bell duration
    parser.feed("\x1b[9;5]")  # screen-blank timeout (minutes)
    parser.feed("\x1b[14;30]")  # VESA powerdown
    parser.feed("\x1b[16;250]")  # cursor blink interval
    assert (board.bell_hz, board.bell_ms) == (440, 200)
    assert board.blank_timeout == 5
    assert board.vesa_powerdown == 30
    assert board.cursor_blink_ms == 250


def test_setterm_console_switch_is_a_signal():
    terminal, parser = _term()
    parser.feed("\x1b[12;3]")  # bring console 3 to the front
    parser.feed("\x1b[15]")  # bring the previous console to the front
    assert terminal.board.console_requests == [("switch", 3), ("previous", 0)]


def test_setterm_8_sets_default_attributes_for_sgr_reset():
    terminal, parser = _term()
    parser.feed("\x1b[31m")  # red
    parser.feed("\x1b[8]")  # make red the default
    parser.feed("\x1b[34m")  # blue
    parser.feed("\x1b[0m")  # SGR reset -> back to the default (red), not blank
    assert terminal.board.style.current.fg == Color("indexed", 1)


def test_default_attributes_cleared_on_ris():
    terminal, parser = _term()
    parser.feed("\x1b[31m\x1b[8m")  # (harmless) then set default via ESC[8]
    parser.feed("\x1b[31m\x1b[8]")  # red as default
    parser.feed("\x1bc")  # RIS clears the default register
    parser.feed("\x1b[34m\x1b[0m")  # blue, then reset -> plain default, not red
    assert terminal.board.style.current.fg is None
