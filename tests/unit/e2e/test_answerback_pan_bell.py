"""ENQ answerback, ECMA-48 SL/SR panning, and DEC bell-volume registers."""

from bittty.parser import Parser
from bittty import Board


class RecordingTransport:
    def __init__(self):
        self.data = []

    def write(self, data):
        self.data.append(data)

    def flush(self):
        pass


def _term():
    terminal = Board(width=10, height=3)
    return terminal, Parser(terminal.board)


def test_enq_transmits_the_answerback_string():
    terminal, parser = _term()
    transport = RecordingTransport()
    terminal.board.host.attach(transport)
    terminal.board.answerback = "bittty"

    parser.feed("\x05")  # ENQ
    assert "".join(transport.data) == "bittty"


def test_enq_sends_nothing_when_unset():
    terminal, parser = _term()
    transport = RecordingTransport()
    terminal.board.host.attach(transport)

    parser.feed("\x05")  # ENQ with the default empty answerback
    assert transport.data == []


def test_scroll_left_pans_data_left():
    terminal, parser = _term()
    parser.feed("ABCDE")  # row 0: "ABCDE"
    parser.feed("\x1b[2 @")  # SL 2 — data moves two columns left
    assert terminal.board.blitter.current_buffer.get_line_text(0).rstrip() == "CDE"


def test_scroll_right_pans_data_right():
    terminal, parser = _term()
    parser.feed("ABCDE")
    parser.feed("\x1b[2 A")  # SR 2 — data moves two columns right
    assert terminal.board.blitter.current_buffer.get_line_text(0).rstrip() == "  ABCDE"


def test_scroll_left_defaults_to_one_column():
    terminal, parser = _term()
    parser.feed("ABCDE")
    parser.feed("\x1b[ @")  # SL with no parameter -> 1
    assert terminal.board.blitter.current_buffer.get_line_text(0).rstrip() == "BCDE"


def test_bell_volume_registers():
    terminal, parser = _term()
    parser.feed("\x1b[3 t")  # DECSWBV — warning bell volume
    parser.feed("\x1b[5 u")  # DECSMBV — margin bell volume
    assert terminal.board.warning_bell_volume == 3
    assert terminal.board.margin_bell_volume == 5
