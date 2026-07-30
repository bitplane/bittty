"""Media Copy (MC): the printer device and its attachable sink."""

import io

from bittty import Board, MemoryPrinter, PrinterStatus
from bittty.parser import Parser


def _term(width=6, height=3):
    board = Board(width=width, height=height)
    return board, Parser(board)


def _line(board, y=0):
    return board.blitter.current_buffer.get_line_text(y).rstrip()


def test_print_screen_dumps_the_buffer_to_the_sink():
    board, parser = _term()
    paper = io.StringIO()
    board.printer.attach(paper)
    parser.feed("HI")
    parser.feed("\x1b[0i")  # MC 0 — print screen
    assert paper.getvalue() == "HI\r\n\r\n\r\n"


def test_printer_controller_mode_tees_text_to_paper_not_screen():
    board, parser = _term()
    paper = io.StringIO()
    board.printer.attach(paper)
    parser.feed("\x1b[5i")  # MC 5 — enter printer controller mode
    parser.feed("hello")  # goes to paper
    parser.feed("\x1b[4i")  # MC 4 — exit controller mode
    parser.feed("world")  # goes to the screen
    assert paper.getvalue() == "hello"
    assert _line(board) == "world"


def test_auto_print_sends_each_line_as_the_cursor_leaves_it():
    board, parser = _term()
    paper = io.StringIO()
    board.printer.attach(paper)
    parser.feed("\x1b[?5i")  # DEC MC 5 — auto-print on
    parser.feed("AB\r\n")  # line feed prints the line being left
    parser.feed("CD\r\n")
    parser.feed("\x1b[?4i")  # auto-print off
    assert paper.getvalue() == "AB\r\nCD\r\n"


def test_dec_print_cursor_line():
    board, parser = _term()
    paper = io.StringIO()
    board.printer.attach(paper)
    parser.feed("XY")
    parser.feed("\x1b[?1i")  # DEC MC 1 — print the cursor line
    assert paper.getvalue() == "XY\r\n"


def test_decpff_appends_form_feed_to_page_prints_only():
    board, parser = _term()
    paper = io.StringIO()
    board.printer.attach(paper)
    parser.feed("XY\x1b[?18h\x1b[0i")
    assert paper.getvalue() == "XY\r\n\r\n\r\n\f"

    paper.seek(0)
    paper.truncate()
    parser.feed("\x1b[?1i")  # cursor-line printing is not a page print
    assert paper.getvalue() == "XY\r\n"

    paper.seek(0)
    paper.truncate()
    parser.feed("\x1b[?18l\x1b[0i")
    assert paper.getvalue() == "XY\r\n\r\n\r\n"


def test_decpex_selects_page_or_scrolling_region_for_ansi_print_page():
    board, parser = _term(height=4)
    paper = io.StringIO()
    board.printer.attach(paper)
    parser.feed("top\r\none\r\ntwo\r\nbottom")
    parser.feed("\x1b[2;3r\x1b[?19l\x1b[0i")
    assert paper.getvalue() == "one\r\ntwo\r\n"

    paper.seek(0)
    paper.truncate()
    parser.feed("\x1b[?19h\x1b[0i")
    assert paper.getvalue() == "top\r\none\r\ntwo\r\nbottom\r\n"


def test_dec_composed_screen_print_ignores_decpex():
    board, parser = _term(height=4)
    paper = io.StringIO()
    board.printer.attach(paper)
    parser.feed("top\r\none\r\ntwo\r\nbottom")
    parser.feed("\x1b[2;3r\x1b[?19l\x1b[?10i")
    assert paper.getvalue() == "top\r\none\r\ntwo\r\nbottom\r\n"


def test_a_callable_sink_is_supported():
    board, parser = _term()
    captured = []
    board.printer.attach(captured.append)
    parser.feed("ok")
    parser.feed("\x1b[0i")
    assert captured == ["ok\r\n\r\n\r\n"]


def test_unattached_printer_absorbs_output_silently():
    board, parser = _term()
    parser.feed("\x1b[5i")  # controller mode with no sink attached
    parser.feed("into the void")
    parser.feed("\x1b[4i")
    assert _line(board) == ""  # nothing reached the screen, and nothing raised


def test_ris_clears_printer_modes_but_keeps_the_sink():
    board, parser = _term()
    paper = io.StringIO()
    board.printer.attach(paper)
    parser.feed("\x1b[5i")  # controller mode on
    parser.feed("\x1bc")  # RIS
    assert board.printer.controller_mode is False
    assert board.printer.print_form_feed is False
    assert board.printer.print_extent is False
    assert board.printer.sink is paper  # config survives a reset


def test_raw_controller_mode_preserves_bytes_and_filters_flow_control():
    board, _ = _term(width=20)
    printer = MemoryPrinter()
    board.printer.attach(printer)

    board.feed_host_data(b"screen\x1b[5i\xff\x00raw\x11\x13\x1b[4iafter")

    assert bytes(printer.data) == b"\xff\x00raw"
    assert board.capture_text() == "screenafter"


def test_controller_sequences_can_be_split_at_every_byte():
    board, _ = _term(width=20)
    printer = MemoryPrinter()
    board.printer.attach(printer)
    data = b"A\x1b[5iprint me\x1b[4iB"

    for byte in data:
        board.feed_host_data(bytes((byte,)))

    assert bytes(printer.data) == b"print me"
    assert board.capture_text() == "AB"


def test_normal_host_utf8_is_incrementally_decoded_around_raw_router():
    board, _ = _term(width=20)
    encoded = "A\N{BALLOT X}B".encode()

    for byte in encoded:
        board.feed_host_data(bytes((byte,)))

    assert board.capture_text() == "A\N{BALLOT X}B"


def test_eight_bit_csi_and_multiple_controller_transitions():
    board, _ = _term(width=20)
    printer = MemoryPrinter()
    board.printer.attach(printer)

    board.feed_host_data(b"A\x9b5ione\x9b4iB\x1b[5itwo\x1b[4iC")

    assert bytes(printer.data) == b"onetwo"
    assert board.capture_text() == "ABC"


def test_controller_mode_forwards_escape_sequences_without_answering_them():
    board, _ = _term()
    printer = MemoryPrinter()
    host = RecordingByteHost()
    board.printer.attach(printer)
    board.host.attach(host)

    board.feed_host_data(b"\x1b[5i\x1b[?15n\x1b[31mraw\x1b[4i")

    assert bytes(printer.data) == b"\x1b[?15n\x1b[31mraw"
    assert host.data == []


class RecordingByteHost:
    def __init__(self):
        self.data = []
        self.flush_count = 0

    def write(self, data):
        self.data.append(data)

    def write_bytes(self, data):
        self.data.append(data)

    def flush(self):
        self.flush_count += 1


def test_printer_status_dsr_and_detached_status():
    board, parser = _term()
    host = RecordingByteHost()
    board.host.attach(host)

    parser.feed("\x1b[?15n")
    assert host.data[-1] == "\x1b[?13n"

    printer = MemoryPrinter(status=PrinterStatus.BUSY)
    board.printer.attach(printer)
    parser.feed("\x1b[?15n")
    assert host.data[-1] == "\x1b[?18n"


def test_printer_to_host_modes_and_filtering():
    board, parser = _term()
    host = RecordingByteHost()
    board.host.attach(host)

    board.printer.receive_bytes(b"ignored")
    parser.feed("\x1b[6i")
    board.printer.receive_bytes(b"A\x00\x11\x13B")
    parser.feed("\x1b[7i")
    board.printer.receive_bytes(b"ignored")
    parser.feed("\x1b[?9i")
    board.printer.receive_bytes(b"C")
    parser.feed("\x1b[?8i")

    assert host.data == [b"A\x00B", b"C"]


def test_mc2_sends_composed_screen_data_to_host():
    board, parser = _term()
    host = RecordingByteHost()
    board.host.attach(host)
    parser.feed("hello\x1b[2i")
    assert host.data[-1] == b"hello\r\n\r\n\r\n"


def test_controller_entry_cancels_auto_print():
    board, _ = _term()
    board.printer.auto_print = True
    board.feed_host_data(b"\x1b[5i")
    assert board.printer.auto_print is False


def test_auto_print_preserves_the_triggering_control_and_wrap_uses_lf():
    board, parser = _term(width=3, height=3)
    printer = MemoryPrinter()
    board.printer.attach(printer)
    parser.feed("\x1b[?5iAB\r\x0bCD\r\x0cXYZQ")
    assert bytes(printer.data) == b"AB\r\x0bCD\r\x0cXYZ\r\n"


def test_composed_output_encoding_is_configurable():
    board, parser = _term()
    printer = MemoryPrinter()
    board.printer.attach(printer, encoding="utf-16-le")
    parser.feed("\N{BALLOT X}\x1b[?1i")
    assert bytes(printer.data) == "\N{BALLOT X}\r\n".encode("utf-16-le")
