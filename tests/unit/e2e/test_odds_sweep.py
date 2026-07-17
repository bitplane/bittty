"""DECSACE attribute-change extent + OSC 5/6 special colours + OSC 15/16/18 Tektronix colours."""

from bittty.parser import Parser
from bittty import Board


class RecordingTransport:
    def __init__(self):
        self.data = []

    def write(self, data):
        self.data.append(data)

    def flush(self):
        pass


def _term(width=6, height=3):
    terminal = Board(width=width, height=height)
    transport = RecordingTransport()
    terminal.board.host.attach(transport)
    return terminal, Parser(terminal.board), transport


# --- DECSACE --- #


def test_deccara_rectangle_extent_is_the_default():
    terminal, parser, _ = _term()
    parser.feed("\x1b[1;2;2;4;1$r")  # DECCARA bold over rows 1-2, cols 2-4 (rectangle)
    buf = terminal.board.screen.current_buffer
    assert buf.get_cell(0, 0)[0].bold is None  # outside the rectangle
    assert buf.get_cell(1, 0)[0].bold is True  # inside (col 2 -> index 1)
    assert buf.get_cell(5, 0)[0].bold is None  # outside on the right


def test_decsace_stream_extent_wraps():
    terminal, parser, _ = _term()
    parser.feed("\x1b[1*x")  # DECSACE 1 -> stream
    assert terminal.board.screen.attr_change_extent == "stream"
    # stream from (row1,col2) to (row1,col4) = linear indices 1..3 on a width-6 row,
    # but a stream to (row2,col2) wraps across the full width
    parser.feed("\x1b[1;5;2;2;1$r")  # start (r1,c5)=idx4, end (r2,c2)=idx7 -> cols 4,5,0,1
    buf = terminal.board.screen.current_buffer
    assert buf.get_cell(4, 0)[0].bold is True
    assert buf.get_cell(5, 0)[0].bold is True  # wrapped past the right edge
    assert buf.get_cell(0, 1)[0].bold is True  # onto the next row
    assert buf.get_cell(1, 1)[0].bold is True
    assert buf.get_cell(2, 1)[0].bold is None  # stops at the stream end


def test_decsace_resets_to_rectangle():
    terminal, parser, _ = _term()
    parser.feed("\x1b[1*x")  # stream
    parser.feed("\x1b[2*x")  # rectangle
    assert terminal.board.screen.attr_change_extent == "rectangle"


# --- OSC special / Tektronix colours --- #


def test_osc_5_special_colour_roundtrip():
    terminal, parser, transport = _term()
    parser.feed("\x1b]5;0;rgb:ffff/0000/0000\x07")  # special colour 0 (bold) = red
    assert terminal.board.palette.special_colors[0] == (255, 0, 0)
    parser.feed("\x1b]5;0;?\x07")
    assert transport.data[-1] == "\x1b]5;0;rgb:ffff/0000/0000\x07"


def test_osc_6_special_colour_enable():
    terminal, parser, _ = _term()
    parser.feed("\x1b]6;1;1\x07")  # enable special colour 1
    assert terminal.board.palette.special_color_enabled[1] is True
    parser.feed("\x1b]6;1;0\x07")
    assert terminal.board.palette.special_color_enabled[1] is False


def test_osc_15_tek_foreground():
    terminal, parser, _ = _term()
    parser.feed("\x1b]15;rgb:1010/2020/3030\x07")  # Tektronix foreground
    assert terminal.board.palette.tek_foreground == (0x10, 0x20, 0x30)
    parser.feed("\x1b]115\x07")  # reset it
    assert terminal.board.palette.tek_foreground is None
