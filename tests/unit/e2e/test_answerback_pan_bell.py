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
    board = Board(width=10, height=3)
    return board, Parser(board)


def test_enq_transmits_the_answerback_string():
    board, parser = _term()
    transport = RecordingTransport()
    board.host.attach(transport)
    board.answerback = "bittty"

    parser.feed("\x05")  # ENQ
    assert "".join(transport.data) == "bittty"


def test_enq_sends_nothing_when_unset():
    board, parser = _term()
    transport = RecordingTransport()
    board.host.attach(transport)

    parser.feed("\x05")  # ENQ with the default empty answerback
    assert transport.data == []


def test_scroll_left_pans_data_left():
    board, parser = _term()
    parser.feed("ABCDE")  # row 0: "ABCDE"
    parser.feed("\x1b[2 @")  # SL 2 — data moves two columns left
    assert board.blitter.current_buffer.get_line_text(0).rstrip() == "CDE"


def test_scroll_right_pans_data_right():
    board, parser = _term()
    parser.feed("ABCDE")
    parser.feed("\x1b[2 A")  # SR 2 — data moves two columns right
    assert board.blitter.current_buffer.get_line_text(0).rstrip() == "  ABCDE"


def test_scroll_left_defaults_to_one_column():
    board, parser = _term()
    parser.feed("ABCDE")
    parser.feed("\x1b[ @")  # SL with no parameter -> 1
    assert board.blitter.current_buffer.get_line_text(0).rstrip() == "BCDE"


def test_bell_volume_registers():
    board, parser = _term()
    parser.feed("\x1b[3 t")  # DECSWBV — warning bell volume
    parser.feed("\x1b[5 u")  # DECSMBV — margin bell volume
    assert board.warning_bell_volume == 3
    assert board.margin_bell_volume == 5
