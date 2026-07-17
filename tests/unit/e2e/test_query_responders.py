"""DECRQCRA rectangle checksum and XTGETTCAP termcap query responders."""

from bittty.parser import Parser
from bittty import Board


class RecordingTransport:
    def __init__(self):
        self.data = []

    def write(self, data):
        self.data.append(data)

    def flush(self):
        pass


def _term(width=10, height=3):
    terminal = Board(width=width, height=height)
    transport = RecordingTransport()
    terminal.board.host.attach(transport)
    return terminal, Parser(terminal.board), transport


def _reply(transport):
    return "".join(transport.data)


def test_decrqcra_checksums_a_rectangle():
    terminal, parser, transport = _term()
    parser.feed("AB")  # cells (0,0)=A (1,0)=B
    parser.feed("\x1b[1;1;1;1;1;2*y")  # DECRQCRA pid=1, rows/cols 1..1 / 1..2
    # negated 16-bit sum of 'A'(65) + 'B'(66) = -(131) & 0xFFFF = 0xFF7D
    assert _reply(transport) == "\x1bP1!~FF7D\x1b\\"


def test_decrqcra_defaults_to_full_screen():
    terminal, parser, transport = _term(width=4, height=2)
    parser.feed("\x1b[1*y")  # pid=1, rectangle omitted -> whole screen (8 spaces)
    # 8 * 0x20 = 256; -(256) & 0xFFFF = 0xFF00
    assert _reply(transport) == "\x1bP1!~FF00\x1b\\"


def _decode_tcap(reply):
    """Parse a DCS <status> + r <name>[=<value>] ST reply into (ok, name, value)."""
    body = reply[len("\x1bP") : -len("\x1b\\")]
    ok = body[0] == "1"
    name_hex, sep, value_hex = body[3:].partition("=")
    name = bytes.fromhex(name_hex).decode("ascii")
    value = bytes.fromhex(value_hex).decode("ascii") if sep else None
    return ok, name, value


def test_xtgettcap_answers_terminal_name():
    terminal, parser, transport = _term()  # default model is xterm
    parser.feed("\x1bP+q" + "TN".encode().hex() + "\x1b\\")
    assert _decode_tcap(_reply(transport)) == (True, "TN", "xterm")


def test_xtgettcap_answers_colour_count():
    terminal, parser, transport = _term()
    parser.feed("\x1bP+q" + "Co".encode().hex() + "\x1b\\")
    assert _decode_tcap(_reply(transport)) == (True, "Co", "256")


def test_xtgettcap_refuses_unknown_capability():
    terminal, parser, transport = _term()
    parser.feed("\x1bP+q5a5a\x1b\\")  # "ZZ" — not a capability we answer
    reply = _reply(transport)
    assert reply == "\x1bP0+r5a5a\x1b\\"


def test_xtgettcap_answers_multiple_capabilities():
    terminal, parser, transport = _term()
    query = "TN".encode().hex() + ";" + "Co".encode().hex()
    parser.feed("\x1bP+q" + query + "\x1b\\")
    replies = _reply(transport).split("\x1b\\")
    decoded = [_decode_tcap(r + "\x1b\\") for r in replies if r]
    assert (True, "TN", "xterm") in decoded
    assert (True, "Co", "256") in decoded
