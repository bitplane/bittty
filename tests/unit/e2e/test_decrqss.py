"""DECRQSS (DCS $q ... ST): reporting the current setting back to the host."""

from bittty import Board
from bittty.model import VT510
from bittty.parser import Parser


class RecordingTransport:
    def __init__(self):
        self.data = []

    def write(self, data):
        self.data.append(data)

    def flush(self):
        pass


def _driver(model=None):
    board = Board(width=80, height=24, model=model)
    transport = RecordingTransport()
    board.host.attach(transport)
    return Parser(board), transport


def test_decrqss_reports_current_sgr():
    parser, transport = _driver()
    parser.feed("\x1b[1;31m")  # bold, red
    parser.feed("\x1bP$qm\x1b\\")  # DECRQSS for SGR
    assert transport.data == ["\x1bP1$r1;31m\x1b\\"]


def test_decrqss_reports_default_sgr_as_zero():
    parser, transport = _driver()
    parser.feed("\x1bP$qm\x1b\\")
    assert transport.data == ["\x1bP1$r0m\x1b\\"]


def test_decrqss_reports_scroll_region():
    parser, transport = _driver()
    parser.feed("\x1b[3;20r")  # DECSTBM
    parser.feed("\x1bP$qr\x1b\\")
    assert transport.data == ["\x1bP1$r3;20r\x1b\\"]


def test_decrqss_reports_cursor_style():
    parser, transport = _driver()
    parser.feed("\x1b[4 q")  # steady underline
    parser.feed("\x1bP$q q\x1b\\")
    assert transport.data == ["\x1bP1$r4 q\x1b\\"]


def test_decrqss_unsupported_request_reports_invalid():
    parser, transport = _driver()
    parser.feed("\x1bP$qZ\x1b\\")  # not a setting we can report
    assert transport.data == ["\x1bP0$rZ\x1b\\"]


def test_vt510_printer_settings_use_dec_framing_and_restorable_payloads():
    parser, transport = _driver(VT510)
    parser.feed("\x1b[2$s\x1b[3)p\x1b[850*p\x1b[2;1*u\x1b[3;7*r")
    for request in ("$s", ")p", "*p", "*u", "*r", "+w"):
        parser.feed(f"\x1bP$q{request}\x1b\\")

    assert transport.data == [
        "\x1bP0$r2$s\x1b\\",
        "\x1bP0$r3)p\x1b\\",
        "\x1bP0$r850*p\x1b\\",
        "\x1bP0$r2;1*u\x1b\\",
        "\x1bP0$r3;7*r\x1b\\",
        "\x1bP0$r2;1;1;1+w\x1b\\",
    ]


def test_flow_control_decrqss_emits_transmit_then_receive():
    parser, transport = _driver(VT510)
    parser.feed("\x1b[2;1;4;1*s\x1b[2;2;2;1*s")
    parser.feed("\x1bP$q*s\x1b\\")
    assert transport.data == [
        "\x1bP0$r2;1;4;1*s\x1b\\",
        "\x1bP0$r2;2;2;1*s\x1b\\",
    ]


def test_vt510_decrqss_uses_dec_validity_for_existing_and_invalid_settings():
    parser, transport = _driver(VT510)
    parser.feed("\x1bP$qm\x1b\\\x1bP$qZ\x1b\\")
    assert transport.data == ["\x1bP0$r0m\x1b\\", "\x1bP1$r\x1b\\"]


def test_non_configurable_model_does_not_expose_attached_configuration():
    from bittty.model import XTERM
    from bittty.printers import MemoryPrinter

    parser, transport = _driver(XTERM)
    parser.sink.printer.attach(MemoryPrinter())
    parser.feed("\x1bP$q$s\x1b\\")
    assert transport.data == ["\x1bP0$r$s\x1b\\"]
