"""DECRQSS (DCS $q ... ST): reporting the current setting back to the host."""

import pytest

from bittty import Board, MemoryConnection
from bittty.model import VT510
from bittty.parser import Parser


def _driver(model=None):
    board = Board(width=80, height=24, model=model)
    transport = MemoryConnection()
    board.host.attach(transport)
    return Parser(board), transport


def test_decrqss_reports_current_sgr():
    parser, transport = _driver()
    parser.feed("\x1b[1;31m")  # bold, red
    parser.feed("\x1bP$qm\x1b\\")  # DECRQSS for SGR
    assert transport.data == ["\x1bP1$r0;1;31m\x1b\\"]


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
    from bittty import MemoryPrinter
    from bittty.model import XTERM

    parser, transport = _driver(XTERM)
    parser.sink.printer.attach(MemoryPrinter())
    parser.feed("\x1bP$q$s\x1b\\")
    assert transport.data == ["\x1bP0$r$s\x1b\\"]


@pytest.mark.parametrize(
    ("setup", "setting", "reply"),
    [
        ("\x1b[?69h\x1b[5;40s", "s", "5;40s"),  # DECSLRM
        ("", "s", "1;80s"),  # reported even with margin mode off
        ("", "t", "24t"),  # DECSLPP
        ("", "*|", "24*|"),  # DECSNLS
        ("", "$|", "80$|"),  # DECSCPP
        ('\x1b[1"q', '"q', '1"q'),  # DECSCA
        ('\x1b[1"q\x1b[2"q', '"q', '0"q'),
        ("", "*x", "0*x"),  # DECSACE powers on as stream
        ("\x1b[2*x", "*x", "2*x"),
        ('\x1b[63;1"p', '"p', '63;1"p'),  # DECSCL: 7-bit controls
        ('\x1b[62"p', '"p', '62;0"p'),  # a bare level selects 8-bit controls
        ('\x1b[63;2"p', '"p', '63;0"p'),
    ],
)
def test_decrqss_reports_settings_as_xterm_does(setup, setting, reply):
    """Replies captured from xterm 407 (80x24)."""
    parser, transport = _driver()
    parser.feed(setup)
    parser.feed(f"\x1bP$q{setting}\x1b\\")
    assert transport.data == [f"\x1bP1$r{reply}\x1b\\"]


@pytest.mark.parametrize(
    ("sgr", "reply"),
    [
        ("1", "0;1m"),
        ("6", "0;5m"),
        ("38;5;9", "0;91m"),
        ("48;5;9", "0;101m"),
        ("38;5;16", "0;38:5:16m"),
        ("38;2;1;2;3", "0;38:2::1:2:3m"),
        ("38:2::1:2:3", "0;38:2::1:2:3m"),
        ("38:2:1:2:3", "0;38:2::1:2:3m"),  # no colour-space field
        ("38:2:0:1:2:3", "0;38:2::1:2:3m"),
        ("48:2::1:2:3", "0;48:2::1:2:3m"),
        ("38:2::1:2:3;48:5:7", "0;38:2::1:2:3;47m"),
        ("38;2;1;2;3;4", "0;4;38:2::1:2:3m"),  # RGB takes exactly three
        ("38;2;1;2", "0;38:2::1:2:0m"),  # missing components are 0
        ("38:2:::1:2", "0;38:2::0:1:2m"),  # so are empty colon arguments
        ("38;5;;1", "0;1m"),  # but an empty semicolon argument voids the colour it belongs to
        ("38;2;;1;2;3", "0;3m"),
        ("48;2;1;;", "0m"),
        ("38;5", "0;30m"),
        ("38:5:", "0;30m"),
        ("38:5", "0m"),
        ("38:2", "0m"),
        ("38:2::300:2:3", "0m"),  # out of range: ignored
        ("38;5;300", "0m"),
        ("31;39", "0m"),
        ("59", "0m"),
        ("4;24", "0m"),
    ],
)
def test_decrqss_reports_sgr_as_xterm_does(sgr, reply):
    """Replies captured from xterm 407."""
    parser, transport = _driver()
    parser.feed(f"\x1b[{sgr}m\x1bP$qm\x1b\\")
    assert transport.data == [f"\x1bP1$r{reply}\x1b\\"]


@pytest.mark.parametrize("sgr", ["38;5;;1", "38;2;;1;2;3", "38;5;<", "38:5:x", "48;2;1;;"])
def test_malformed_colour_arguments_do_not_raise(sgr):
    parser, transport = _driver()
    parser.feed(f"\x1b[{sgr}m\x1bP$qm\x1b\\")
    assert transport.data[0].startswith("\x1bP1$r")


def test_sgr_4_is_a_single_underline_again():
    """4 means 4:1 (kitty), so it replaces a curly underline rather than keeping its style."""
    parser, transport = _driver()
    parser.feed("\x1b[4:3m\x1b[4m\x1bP$qm\x1b\\")
    assert transport.data == ["\x1bP1$r0;4m\x1b\\"]
