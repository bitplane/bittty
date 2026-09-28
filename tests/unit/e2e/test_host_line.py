"""The VT510's host line: DECSCS, DECSFC, DECSPP, DECSCP and DECSTRL select its settings, and
DECXRLM (73), DECMCM (99) and DECHDPXM (103) its modes.

The terminal holds the line's configuration whatever is on the cable, as it holds the printer's,
and offers it to a connection that can apply it (a serial port could; a PTY has no modem).
Defaults are the VT510's factory Set-Up (reference manual 2.9 and table 2-10). xterm 407 reports
DECXRLM permanently reset (captured).
"""

from dataclasses import replace

import pytest

from bittty import Board, MemoryConnection
from bittty.model import VT510, XTERM
from bittty.serial_line import FlowControl, FlowThreshold, HostPortSelection, Parity, SerialLine


def _run(sequence, model=VT510):
    board = Board(width=40, height=4, model=model)
    wire = MemoryConnection()
    board.host.attach(wire)
    board.feed_host_data(sequence)
    return board, wire


def test_factory_settings():
    board, _ = _run("")
    assert board.comm.line == SerialLine(
        port=HostPortSelection.COMM1,
        transmit_baud=9600,
        receive_baud=None,  # the receive speed follows the transmit speed
        data_bits=8,
        parity=Parity.NONE,
        stop_bits=1,
        transmit_flow_control=FlowControl.NONE,
        receive_flow_control=FlowControl.XON_XOFF,
        flow_threshold=FlowThreshold.LOW,
        transmit_rate_limit=150,
        function_key_rate_limit=150,
    )


@pytest.mark.parametrize(
    ("sequence", "changes"),
    [
        ("\x1b[1;8*r", {"transmit_baud": 38400}),  # DECSCS: host transmit
        ("\x1b[;3*r", {"transmit_baud": 1200}),
        ("\x1b[2;4*r", {"receive_baud": 2400}),  # host receive
        ("\x1b[1;2;3;2*s", {"receive_flow_control": FlowControl.BOTH, "flow_threshold": FlowThreshold.HIGH}),
        ("\x1b[1;3;4*s", {"transmit_flow_control": FlowControl.NONE, "receive_flow_control": FlowControl.NONE}),
        ("\x1b[1;2;3;2+w", {"data_bits": 7, "parity": Parity.ODD, "stop_bits": 2}),  # DECSPP
        ("\x1b[;;5+w", {"parity": Parity.ODD_UNCHECKED}),
        ("\x1b[1;2*u", {"port": HostPortSelection.COMM2}),  # DECSCP: the host on comm2
        ('\x1b[3;2"u', {"function_key_rate_limit": 50}),  # DECSTRL: function keys at 50 cps
        ('\x1b[;3"u', {"transmit_rate_limit": 30, "function_key_rate_limit": 30}),  # all keys
        ('\x1b[2;3"u\x1b[3;2"u', {"transmit_rate_limit": 30, "function_key_rate_limit": 50}),
        ("\x1b[?73h", {"rate_limited": True}),
        ("\x1b[?99h", {"modem_control": True}),
        ("\x1b[?103h", {"half_duplex": True}),
    ],
)
def test_settings(sequence, changes):
    board, _ = _run(sequence)
    assert board.comm.line == replace(SerialLine(), **changes)


@pytest.mark.parametrize(
    "sequence",
    [
        "\x1b[1;99*r",  # no such speed
        "\x1b[1;3;9*s",  # no such flow control
        "\x1b[1;3;1;3*s",  # no such threshold
        "\x1b[1;3+w",  # no such word size
        "\x1b[1;1;8+w",  # no such parity
        "\x1b[1;3*u",  # no third host port
        '\x1b[1;4"u',  # no such rate
        '\x1b[4;1"u',  # no such key type
    ],
)
def test_invalid_settings_are_ignored(sequence):
    board, _ = _run(sequence)
    assert board.comm.line == SerialLine()


def test_printer_selectors_leave_the_host_line_alone():
    board, _ = _run("\x1b[3;7*r\x1b[2;3;4;1*s\x1b[2;2;3;2+w\x1b[2;1*u")
    assert board.comm.line == SerialLine()
    assert board.printer.configuration.baud_rate == 19200


def test_the_connection_is_offered_the_line_and_each_change():
    board, wire = _run("")
    board.feed_host_data("\x1b[1;8*r\x1b[1;8*r\x1b[?103h")
    faster = replace(SerialLine(), transmit_baud=38400)
    assert wire.lines == [SerialLine(), faster, replace(faster, half_duplex=True)]  # the whole line on attach


def test_ris_keeps_the_set_up():
    board, _ = _run("\x1b[1;8*r\x1b[?103h\x1bc")
    assert board.comm.line == replace(SerialLine(), transmit_baud=38400, half_duplex=True)


@pytest.mark.parametrize(
    ("request_", "replies"),
    [
        ("*r", ["1;6*r", "2;6*r", "3;5*r"]),  # host transmit, host receive (following it), printer
        ("*s", ["1;1;4;1*s", "1;2;1;1*s", "2;1;1;1*s", "2;2;1;1*s"]),
        ("+w", ["1;1;1;1+w", "2;1;1;1+w"]),
        ("*u", ["1;1*u"]),
        ('"u', ['2;1"u', '3;1"u']),
    ],
)
def test_decrqss_reports_both_ports(request_, replies):
    _, wire = _run(f"\x1bP$q{request_}\x1b\\")
    assert wire.data == [f"\x1bP0$r{reply}\x1b\\" for reply in replies]


@pytest.mark.parametrize(("sequence", "status"), [("", 2), ("\x1b[?73h", 1)])
def test_decrqm(sequence, status):
    _, wire = _run(sequence + "\x1b[?73$p\x1b[?99$p\x1b[?103$p")
    assert wire.data == [f"\x1b[?73;{status}$y", "\x1b[?99;2$y", "\x1b[?103;2$y"]


def test_xterm_has_no_host_line_settings():
    board, wire = _run("\x1b[1;8*r\x1b[?99h\x1b[?99$p", XTERM)
    assert wire.data == ["\x1b[?99;0$y"]
    assert board.comm.line == SerialLine()
