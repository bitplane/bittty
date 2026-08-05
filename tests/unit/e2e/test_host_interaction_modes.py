"""Keyboard, answerback, bell-policy, and in-band resize modes."""

import pytest

from bittty import BITTTY, VT100, VT220, VT510, XTERM, Board, MemoryConnection, TerminalCaps
from bittty.parser import Parser
from bittty.present import Bell, KeyboardLockChanged, WindowRequest


class Recorder:
    def __init__(self):
        self.events = []

    def present(self, event):
        self.events.append(event)


def _term(*, width=20, height=4, model=None):
    board = Board(width=width, height=height, model=model)
    transport = MemoryConnection()
    recorder = Recorder()
    board.host.attach(transport)
    board.display.attach(recorder)
    return board, Parser(board), transport, recorder


def test_kam_blocks_keyboard_origins_but_not_focus_or_mouse_reports():
    board, parser, transport, recorder = _term()
    parser.feed("\x1b[?1000h\x1b[?1006h\x1b[?1004h\x1b[2h")

    board.input("x")
    board.input_key("y")
    board.input_fkey(1)
    board.input_numpad_key("1")
    board.input_paste("paste")
    assert transport.data == []

    board.focus_out()
    board.input_mouse(2, 2, 0, "press", set())
    assert transport.data == ["\x1b[O", "\x1b[<0;2;2M"]
    assert KeyboardLockChanged(True) in recorder.events

    parser.feed("\x1b[2l")
    board.input("z")
    assert transport.data[-1] == "z"
    assert KeyboardLockChanged(False) in recorder.events


def test_srm_local_echo_is_direct_and_does_not_render_key_sequences():
    board, parser, transport, _ = _term()
    assert board.modes.local_echo is False
    assert board.modes.get_ansi_mode_status(12) == 1

    parser.feed("\x1b[12l")
    board.input("ab")
    board.input_key("up")
    assert board.capture_text() == "ab"
    assert transport.data[0] == "ab"
    assert transport.data[1].startswith("\x1b[")

    board.input("\b")
    board.input("Z")
    assert board.capture_text() == "aZ"
    assert board.modes.get_ansi_mode_status(12) == 2


def test_kam_soft_reset_and_hard_mode_defaults():
    board, parser, _, _ = _term()
    parser.feed("\x1b[2h\x1b[12l\x1b[!p")
    assert board.modes.keyboard_locked is False
    assert board.modes.local_echo is True

    parser.feed("\x1bc")
    assert board.modes.keyboard_locked is False
    assert board.modes.local_echo is False


@pytest.mark.asyncio
async def test_auto_answerback_fires_only_on_real_connect():
    board = Board(model=VT510)
    board.answerback = "VT510"
    board.modes.set_private_modes((100,), True)

    attached = MemoryConnection()
    board.host.attach(attached)
    assert attached.data == []

    connected = MemoryConnection()
    board.host.connect(connected, board._dispatch_pty_data, on_idle=lambda: True)
    await board.host._reader_task
    assert connected.data == ["VT510"]


@pytest.mark.asyncio
async def test_enabling_auto_answerback_on_a_live_connection_waits_for_reconnect():
    board = Board(model=VT510)
    board.answerback = "hello"
    first = MemoryConnection()
    board.host.connect(first, board._dispatch_pty_data, on_idle=lambda: True)
    await board.host._reader_task
    board.modes.set_private_modes((100,), True)
    assert first.data == []

    second = MemoryConnection()
    board.host.connect(second, board._dispatch_pty_data, on_idle=lambda: True)
    await board.host._reader_task
    assert second.data == ["hello"]


def test_concealed_answerback_stays_transmittable_and_cannot_be_reset():
    board, parser, transport, _ = _term(model=VT510)
    board.answerback = "secret"
    parser.feed("\x1b[?101h\x1b[?101l")

    assert board.answerback is None
    assert board.answerback_concealed is True
    assert board.modes.get_private_mode_status(101) == 1
    parser.feed("\x05")
    assert transport.data == ["secret"]

    parser.feed("\x1bc")
    assert board.answerback is None
    board.answerback = "replacement"
    assert board.answerback == "replacement"
    assert board.answerback_concealed is False
    assert board.modes.get_private_mode_status(101) == 2


def test_margin_bell_rings_once_per_zone_and_rearms_on_a_new_row():
    board, parser, _, recorder = _term(width=20)
    parser.feed("\x1b[?44h")
    board.cursor.set_position(10, 0)
    board.input_key("a")
    board.input_key("b")
    assert recorder.events.count(Bell()) == 1

    board.cursor.set_position(10, 1)
    board.input_key("c")
    assert recorder.events.count(Bell()) == 2

    board.cursor.set_position(0, 1)
    board.input_key("d")
    board.cursor.set_position(10, 1)
    board.input_key("e")
    assert recorder.events.count(Bell()) == 3


def test_bell_window_policies_are_ordered_and_queryable():
    board, parser, _, recorder = _term()
    parser.feed("\x1b[?1042h\x1b[?1043h\x07")
    assert recorder.events[-3:] == [Bell(), WindowRequest("urgent"), WindowRequest("raise")]
    assert board.modes.get_private_mode_status(1042) == 1
    assert board.modes.get_private_mode_status(1043) == 1


def test_inband_resize_reports_enable_reenable_and_frontend_resizes():
    board, parser, transport, _ = _term(width=20, height=4)
    board.set_caps(TerminalCaps(cell_px=(8, 16)))
    parser.feed("\x1b[?2048h\x1b[?2048h")
    assert transport.data[-2:] == [
        "\x1b[48;4;20;64;160t",
        "\x1b[48;4;20;64;160t",
    ]

    board.display.resize(30, 6)
    assert transport.data[-1] == "\x1b[48;6;30;96;240t"
    before = len(transport.data)
    board.resize(40, 8)
    assert len(transport.data) == before


def test_inband_resize_uses_zero_pixels_when_cell_geometry_is_unknown():
    _, parser, transport, _ = _term(width=12, height=3)
    parser.feed("\x1b[?2048h")
    assert transport.data[-1] == "\x1b[48;3;12;0;0t"


def test_new_modes_are_gated_by_audited_model_profiles():
    vt100 = Board(model=VT100).modes
    vt220 = Board(model=VT220).modes
    vt510 = Board(model=VT510).modes
    xterm = Board(model=XTERM).modes
    native = Board(model=BITTTY).modes

    assert vt100.recognizes(False, 2) is False
    assert vt220.recognizes(False, 2) and vt220.recognizes(False, 12)
    assert vt510.recognizes(True, 100) and vt510.recognizes(True, 101)
    assert xterm.recognizes(True, 44) and not xterm.recognizes(True, 100)
    assert native.recognizes(True, 2048)
    assert all(not modes.recognizes(True, 103) for modes in (vt100, vt220, vt510, xterm, native))
