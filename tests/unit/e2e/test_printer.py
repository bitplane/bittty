"""Media Copy (MC): the printer device and its attachable sink."""

import io

from bittty.parser import Parser
from bittty import Board


def _term(width=6, height=3):
    terminal = Board(width=width, height=height)
    return terminal, Parser(terminal.board)


def _line(terminal, y=0):
    return terminal.board.blitter.current_buffer.get_line_text(y).rstrip()


def test_print_screen_dumps_the_buffer_to_the_sink():
    terminal, parser = _term()
    paper = io.StringIO()
    terminal.board.printer.attach(paper)
    parser.feed("HI")
    parser.feed("\x1b[0i")  # MC 0 — print screen
    assert paper.getvalue() == "HI\n\n\n"


def test_printer_controller_mode_tees_text_to_paper_not_screen():
    terminal, parser = _term()
    paper = io.StringIO()
    terminal.board.printer.attach(paper)
    parser.feed("\x1b[5i")  # MC 5 — enter printer controller mode
    parser.feed("hello")  # goes to paper
    parser.feed("\x1b[4i")  # MC 4 — exit controller mode
    parser.feed("world")  # goes to the screen
    assert paper.getvalue() == "hello"
    assert _line(terminal) == "world"


def test_auto_print_sends_each_line_as_the_cursor_leaves_it():
    terminal, parser = _term()
    paper = io.StringIO()
    terminal.board.printer.attach(paper)
    parser.feed("\x1b[?5i")  # DEC MC 5 — auto-print on
    parser.feed("AB\r\n")  # line feed prints the line being left
    parser.feed("CD\r\n")
    parser.feed("\x1b[?4i")  # auto-print off
    assert paper.getvalue() == "AB\nCD\n"


def test_dec_print_cursor_line():
    terminal, parser = _term()
    paper = io.StringIO()
    terminal.board.printer.attach(paper)
    parser.feed("XY")
    parser.feed("\x1b[?1i")  # DEC MC 1 — print the cursor line
    assert paper.getvalue() == "XY\n"


def test_a_callable_sink_is_supported():
    terminal, parser = _term()
    captured = []
    terminal.board.printer.attach(captured.append)
    parser.feed("ok")
    parser.feed("\x1b[0i")
    assert captured == ["ok\n\n\n"]


def test_unattached_printer_absorbs_output_silently():
    terminal, parser = _term()
    parser.feed("\x1b[5i")  # controller mode with no sink attached
    parser.feed("into the void")
    parser.feed("\x1b[4i")
    assert _line(terminal) == ""  # nothing reached the screen, and nothing raised


def test_ris_clears_printer_modes_but_keeps_the_sink():
    terminal, parser = _term()
    paper = io.StringIO()
    terminal.board.printer.attach(paper)
    parser.feed("\x1b[5i")  # controller mode on
    parser.feed("\x1bc")  # RIS
    assert terminal.board.printer.controller_mode is False
    assert terminal.board.printer.sink is paper  # config survives a reset
