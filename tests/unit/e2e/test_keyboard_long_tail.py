"""Wire-level coverage for DECUDK, DECARM and mintty Escape modes.

References: VT220 Programmer Reference, sections 4.15, 4.17 and 4.18;
https://github.com/mintty/mintty/wiki/CtrlSeqs#escape-keycode
"""

import pytest

from bittty import Board, KeyEvent, KeyModifiers
from bittty.connections import MemoryConnection
from bittty.model import BITTTY, KITTY, VT100, VT220, VT510, XTERM
from bittty.terminals import StdioTerminal


def driver(model=BITTTY):
    board = Board(model=model)
    wire = MemoryConnection()
    board.host.attach(wire)
    return board, wire


def define(board, body, params="0;1"):
    board.feed_host_data(f"\x1bP{params}|{body}\x1b\\")


def test_udk_clear_merge_delete_and_shift():
    board, wire = driver()
    define(board, "17/4142;18/43")
    board.input_fkey(6)
    board.input_fkey(6, 2)
    assert wire.data == ["\x1b[17~", b"AB"]
    define(board, "17/44", "1;1")
    assert board.keyboard.user_defined_keys == {6: b"D", 7: b"C"}
    define(board, "17/", "1;1")
    assert board.keyboard.user_defined_keys == {7: b"C"}
    define(board, "19/45")
    assert board.keyboard.user_defined_keys == {8: b"E"}


def test_udk_lock_status_operator_unlock_and_resets():
    board, wire = driver()
    board.feed_host_data("\x1b[?25n")
    define(board, "17/41", "")  # omitted parameters clear, then lock
    board.feed_host_data("\x1b[?25n")
    assert wire.text == "\x1b[?20n\x1b[?21n"
    define(board, "17/42", "1;1")  # cannot unlock from DECUDK
    board.feed_host_data("\x1b[!p")
    assert board.keyboard.user_defined_keys == {6: b"A"}
    assert board.keyboard.user_keys_locked
    board.keyboard.set_user_keys_locked(False)
    define(board, "17/42")
    assert board.keyboard.user_defined_keys == {6: b"B"}
    board.feed_host_data("\x1bc")
    assert board.keyboard.user_defined_keys == {}
    assert not board.keyboard.user_keys_locked


def test_udk_bytes_and_keyboard_lock():
    board, wire = driver()
    define(board, "17/0080ff1b")
    event = KeyEvent("f6", KeyModifiers.SHIFT)
    board.input_key_event(event)
    assert wire.data == [b"\x00\x80\xff\x1b"]
    board.feed_host_data("\x1b[2h")
    board.input_key_event(event)
    assert len(wire.data) == 1


def test_udk_capacity_is_sequential_and_released_by_deletion():
    board, _ = driver(VT220)
    define(board, "17/" + "41" * 250 + ";18/" + "42" * 7)
    assert board.keyboard.user_defined_keys == {6: b"A" * 250}
    define(board, "17/;18/" + "42" * 256, "1;1")
    assert board.keyboard.user_defined_keys == {7: b"B" * 256}


def test_udk_fragmented_bytes_and_screen_switch():
    sequence = b"\x1bP0;1|17/ff0080\x1b\\"
    for split in range(len(sequence) + 1):
        board, wire = driver()
        board.feed_host_data(sequence[:split])
        board.feed_host_data(sequence[split:])
        board.feed_host_data("\x1b[?1049h")
        board.input_key_event(KeyEvent("f6", KeyModifiers.SHIFT))
        board.feed_host_data("\x1b[?1049l")
        board.input_key_event(KeyEvent("f6", KeyModifiers.SHIFT))
        assert wire.data == [b"\xff\x00\x80"] * 2


@pytest.mark.parametrize("params", ["2;1", "1;2", "1;1;1", "$q", "+1", "99"])
def test_invalid_udk_header_does_not_clear_or_lock(params):
    board, _ = driver()
    define(board, "17/41")
    define(board, "17/42", params)
    assert board.keyboard.user_defined_keys == {6: b"A"}
    assert not board.keyboard.user_keys_locked


def test_udk_bad_entries_do_not_become_text_or_replace_valid_keys():
    board, _ = driver()
    define(board, "17/41")
    define(board, "17/GG;18/4;19/4 1;999/43;20/44", "1;1")
    assert board.keyboard.user_defined_keys == {6: b"A", 9: b"D"}
    assert board.capture_text() == ""


@pytest.mark.parametrize(
    "model,supported", [(VT100, False), (KITTY, False), (VT220, True), (VT510, True), (XTERM, True)]
)
def test_udk_repertoire(model, supported):
    board, wire = driver(model)
    define(board, "17/41")
    board.feed_host_data("\x1b[?25n")
    assert bool(board.keyboard.user_defined_keys) == supported
    assert wire.text == ("\x1b[?20n" if supported else "")


def test_kitty_takes_precedence_over_udk_and_escape_modes():
    board, wire = driver()
    define(board, "17/41")
    board.feed_host_data("\x1b[?7727;7728h\x1b[>31u")
    board.input_key_event(KeyEvent("f6", KeyModifiers.SHIFT))
    board.input_key_event(KeyEvent("escape"))
    assert wire.text == "\x1b[17;2~\x1b[27u"


@pytest.mark.parametrize("model", [BITTTY, VT100, VT220, VT510])
def test_auto_repeat_filters_only_explicit_repeats(model):
    board, wire = driver(model)
    board.feed_host_data("\x1b[?8l")
    board.input_key_event(KeyEvent("a", event_type="repeat", text="a"))
    board.input_key_event(KeyEvent("a", text="a"))
    board.input_key("a")  # legacy APIs do not invent repeat facts
    board.input_text("a")
    board.input_paste("a")
    assert wire.text == "aaaa"
    board.feed_host_data("\x1b[?8h")
    board.input_key_event(KeyEvent("a", event_type="repeat", text="a"))
    assert wire.text == "aaaaa"


def test_auto_repeat_filter_precedes_echo_bells_and_kitty_encoding():
    board, wire = driver()
    events = []
    board.present = events.append
    board.feed_host_data("\x1b[12l\x1b[?44h\x1b[?8l\x1b[>31u")
    board.cursor.x = board.width - 1
    events.clear()
    board.input_key_event(KeyEvent("a", event_type="repeat", text="a"))
    assert wire.data == []
    assert events == []
    assert board.capture_text() == ""
    board.input_key_event(KeyEvent("a", event_type="release"))
    assert wire.text == "\x1b[97;1:3u"


@pytest.mark.parametrize("mode,default", [(8, 1), (7727, 2), (7728, 2)])
def test_mode_query_save_restore_screen_and_reset(mode, default):
    board, wire = driver()
    board.feed_host_data(f"\x1b[?{mode}$p\x1b[?{mode}s\x1b[?{mode}{'l' if default == 1 else 'h'}")
    board.feed_host_data("\x1b[?1049h\x1b[?1049l")
    assert board.modes.get_private_mode_status(mode) == 3 - default
    board.feed_host_data(f"\x1b[?{mode}r\x1b[?{mode}$p")
    assert wire.text == f"\x1b[?{mode};{default}$y" * 2
    board.feed_host_data(f"\x1b[?{mode}{'l' if default == 1 else 'h'}\x1bc")
    assert board.modes.get_private_mode_status(mode) == default


def test_xterm_does_not_advertise_new_modes():
    board, wire = driver(XTERM)
    board.feed_host_data("\x1b[?8l\x1b[?7727;7728h")
    for mode in (8, 7727, 7728):
        assert board.modes.get_private_mode_status(mode) == 0
    board.input_key_event(KeyEvent("escape"))
    assert wire.text == "\x1b"


def test_escape_precedence_modifiers_raw_input_and_paste():
    board, wire = driver()
    board.feed_host_data("\x1b[?7728;1039h")
    board.input_key("\x1b")
    board.input_key_event(KeyEvent("escape", KeyModifiers.ALT))
    board.input_key_event(KeyEvent("[", KeyModifiers.CTRL))
    assert wire.text == "\x1c\x1b\x1c\x1b"
    wire.data.clear()
    board.feed_host_data("\x1b[?7727h")
    for mod in (KeyModifiers.NONE, KeyModifiers.SHIFT, KeyModifiers.ALT, KeyModifiers.CTRL):
        board.input_key_event(KeyEvent("escape", mod))
    board.input("\x1b")
    board.input_paste("\x1b")
    assert wire.text == "\x1bO[" * 4 + "\x1b\x1b"
    wire.data.clear()
    board.feed_host_data("\x1b[>4;2m")
    board.input_key_event(KeyEvent("escape", KeyModifiers.CTRL))
    assert wire.text == "\x1b[27;5;27~"


def test_application_escape_distinguishes_keypad_navigation():
    board, wire = driver()
    board.feed_host_data("\x1b=\x1b[?7727h")
    board.input_key_event(KeyEvent("kp_up"))
    board.input_key_event(KeyEvent("up"))
    assert wire.text == "\x1bOx\x1b[A"
    wire.data.clear()
    board.feed_host_data("\x1b[?1h")
    board.input_key_event(KeyEvent("kp_up"))
    assert wire.text == "\x1bOA"


def test_stdio_escape_fragmentation_and_paste():
    terminal = StdioTerminal()
    wire = MemoryConnection()
    terminal.board.host.attach(wire)
    terminal.board.feed_host_data("\x1b[?7728h")
    terminal.handle_input(b"\x1b")
    assert not wire.data
    terminal.flush_pending_input()
    assert wire.text == "\x1c"
    for part in (b"\x1b", b"O", b"["):
        terminal.handle_input(part)
    assert wire.text == "\x1c\x1c"
    terminal.handle_input(b"\x1b[200~\x1b\x1b[201~")
    assert wire.text == "\x1c\x1c\x1b"
