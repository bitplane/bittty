"""Xterm keyboard-selection wire fixtures (input.c and util.c)."""

import pytest

from bittty import Board, KeyEvent, KeyModifiers
from bittty.connections import MemoryConnection
from bittty.keyboard_styles import KeyboardStyle
from bittty.model import BITTTY, KITTY, VT220, XTERM
from bittty.terminals import StdioTerminal

MODES = (1051, 1052, 1053, 1060, 1061)


def driver(mode, model=BITTTY):
    board = Board(model=model)
    wire = MemoryConnection()
    board.host.attach(wire)
    board.feed_host_data(f"\x1b[?{mode}h".encode())
    return board, wire


@pytest.mark.parametrize(
    "mode,key,expected",
    [
        (1051, "f1", "\x1b[224z"),
        (1051, "f10", "\x1b[233z"),
        (1051, "f11", "\x1b[192z"),
        (1051, "f20", "\x1b[201z"),
        (1051, "f21", "\x1b[208z"),
        (1051, "f35", "\x1b[222z"),
        (1051, "f36", "\x1b[234z"),
        (1051, "f37", "\x1b[235z"),
        (1051, "up", "\x1bOA"),
        (1051, "home", "\x1b[214z"),
        (1051, "end", "\x1b[220z"),
        (1051, "pageup", "\x1b[216z"),
        (1051, "pagedown", "\x1b[222z"),
        (1051, "delete", "\x1b[3z"),
        (1051, "help", "\x1b[196z"),
        (1051, "menu", "\x1b[197z"),
        (1052, "f1", "\x1bp"),
        (1052, "f8", "\x1bw"),
        (1052, "f9", "\x1b[20~"),
        (1052, "up", "\x1bA"),
        (1052, "home", "\x1bh"),
        (1052, "end", "\x1bF"),
        (1052, "insert", "\x1bQ"),
        (1052, "delete", "\x1bP"),
        (1052, "pageup", "\x1bT"),
        (1052, "pagedown", "\x1bS"),
        (1053, "f1", "\x1b[M"),
        (1053, "f12", "\x1b[X"),
        (1053, "f13", "\x1b[Y"),
        (1053, "f40", "\x1b[z"),
        (1053, "f41", "\x1b[@"),
        (1053, "f48", "\x1b[{"),
        (1053, "up", "\x1b[A"),
        (1053, "insert", "\x1b[L"),
        (1053, "pageup", "\x1b[I"),
        (1053, "pagedown", "\x1b[G"),
        (1060, "f1", "\x1b[11~"),
        (1060, "f4", "\x1b[14~"),
        (1060, "home", "\x1b[H"),
        (1060, "delete", "\x7f"),
        (1061, "f1", "\x1bOP"),
        (1061, "f13", "\x1b[25~"),
        (1061, "home", "\x1b[1~"),
        (1061, "end", "\x1b[4~"),
        (1061, "delete", "\x1b[3~"),
    ],
)
def test_selected_key_encodings(mode, key, expected):
    board, wire = driver(mode)
    board.input_key_event(KeyEvent(key))
    assert wire.text == expected
    wire.data.clear()
    if key.startswith("f") and key[1:].isdigit():
        board.input_fkey(int(key[1:]))
    else:
        board.input_key(key)
    assert wire.text == expected


@pytest.mark.parametrize(
    "mode,expected",
    [(1051, "\x1b[224;2z"), (1052, "\x1b[1;2p"), (1053, "\x1b[1;2M"), (1060, "\x1b[11~"), (1061, "\x1bOP")],
)
def test_shift_function_key(mode, expected):
    board, wire = driver(mode)
    board.input_key_event(KeyEvent("f1", KeyModifiers.SHIFT))
    assert wire.text == expected


@pytest.mark.parametrize(
    "mode,event,expected",
    [
        (1060, KeyEvent("f1", KeyModifiers.ALT | KeyModifiers.SHIFT), "\x1b[11;4~"),
        (1061, KeyEvent("f1", KeyModifiers.ALT | KeyModifiers.SHIFT), "\x1b[1;4P"),
        (1060, KeyEvent("up", KeyModifiers.SHIFT), "\x1b[1;2A"),
        (1061, KeyEvent("home", KeyModifiers.CTRL), "\x1b[1;5~"),
        (1060, KeyEvent("f1", KeyModifiers.CTRL), "\x1b[23~"),
        (1060, KeyEvent("delete"), "\x7f"),
        (1060, KeyEvent("delete", KeyModifiers.CTRL), "\x1b[3;5~"),
    ],
)
def test_modify_other_keys_unlocks_legacy_modifiers(mode, event, expected):
    """xterm 407: with modifyOtherKeys the legacy/VT220 keyboards fold modifiers in (after the Ctrl-Fn bank)."""
    board, wire = driver(mode)
    board.feed_host_data("\x1b[>4;1m".encode())
    board.input_key_event(event)
    assert wire.text == expected


@pytest.mark.parametrize("mode", [1060, 1061])
def test_legacy_keypad_modifiers_with_modify_other_keys(mode):
    board, wire = driver(mode)
    board.feed_host_data("\x1b[>4;2m\x1b=".encode())
    board.input_key_event(KeyEvent("kp_enter", KeyModifiers.CTRL))
    assert wire.text == "\x1bO5M"


@pytest.mark.parametrize("mode", [1060, 1061])
def test_control_function_bank_and_shift_udk(mode):
    """xterm 407: ctrlFKeys is 10, so Ctrl-F1 is F11 and Ctrl-F10 is F20."""
    board, wire = driver(mode)
    board.feed_host_data("\x1bP0;1|23/4142\x1b\\".encode())
    board.input_key_event(KeyEvent("f1", KeyModifiers.CTRL))
    assert wire.text == "\x1b[23~"
    wire.data.clear()
    board.input_key_event(KeyEvent("f10", KeyModifiers.CTRL))
    assert wire.text == "\x1b[34~"
    wire.data.clear()
    board.input_key_event(KeyEvent("f1", KeyModifiers.CTRL | KeyModifiers.SHIFT))
    assert wire.text == ("AB" if mode == 1061 else "\x1b[23~")


@pytest.mark.parametrize("mode", [1051, 1052, 1053])
def test_other_styles_do_not_apply_udk(mode):
    board, wire = driver(mode)
    board.feed_host_data("\x1bP0;1|17/4142\x1b\\".encode())
    board.input_key_event(KeyEvent("f6", KeyModifiers.SHIFT))
    assert "AB" not in wire.text


@pytest.mark.parametrize(
    "mode,expected", [(1051, "\x1bOA"), (1052, "\x1bA"), (1053, "\x1b[A"), (1060, "\x1bOA"), (1061, "\x1bOA")]
)
def test_cursor_application_interaction(mode, expected):
    board, wire = driver(mode)
    board.feed_host_data("\x1b[?1h".encode())
    board.input_key_event(KeyEvent("up"))
    assert wire.text == expected


@pytest.mark.parametrize("mode", MODES)
def test_selection_query_reset_and_shared_save_slot(mode):
    board, wire = driver(mode)
    assert [board.modes.get_private_mode_status(n) for n in MODES] == [1 if n == mode else 2 for n in MODES]
    board.feed_host_data("\x1b[?1051s\x1b[?1061h\x1b[?1052r".encode())
    assert board.modes.get_private_mode_status(mode) == 1
    board.feed_host_data("\x1b[?1049h\x1b[?1049l\x1b[!p\x1bc".encode())
    assert board.modes.get_private_mode_status(mode) == 1  # xterm keeps keyboard selection on RIS
    board.feed_host_data("\x1b[?1053l".encode())  # reset any member restores default, not just the active one
    assert board.keyboard.style is KeyboardStyle.DEFAULT
    board.feed_host_data("\x1b[?1052r".encode())  # RIS cleared the saved slot
    assert board.keyboard.style is KeyboardStyle.DEFAULT
    assert not wire.data


def test_shared_save_last_writer_and_batched_order():
    board, _ = driver(1051)
    board.feed_host_data("\x1b[?1061s\x1b[?1052h\x1b[?1053s\x1b[?1051h\x1b[?1060r".encode())
    assert board.keyboard.style is KeyboardStyle.HP
    board.feed_host_data("\x1b[?1051;1053;1060h".encode())
    assert board.keyboard.style is KeyboardStyle.LEGACY


def test_legacy_delete_explicit_override_and_save_restore():
    board, wire = driver(1060)
    board.feed_host_data("\x1b[?1037s\x1b[?1037l".encode())
    board.input_key_event(KeyEvent("delete"))
    assert wire.text == "\x1b[3~"
    wire.data.clear()
    board.feed_host_data("\x1b[?1037r".encode())
    board.input_key_event(KeyEvent("delete"))
    assert wire.text == "\x7f"


def test_vt220_keypad_identity_and_arithmetic():
    board, wire = driver(1061)
    for key, mods in [("kp_up", 0), ("kp_add", 0), ("kp_add", 4), ("kp_add", 1)]:
        board.input_key_event(KeyEvent(key, KeyModifiers(mods)))
    assert wire.text == "8,-+"
    wire.data.clear()
    board.feed_host_data("\x1b=\x1b[?1h".encode())
    for key, mods in [("kp_up", 0), ("kp_add", 0), ("kp_add", 4), ("kp_add", 1)]:
        board.input_key_event(KeyEvent(key, KeyModifiers(mods)))
    assert wire.text == "\x1bOx\x1bOl\x1bOm\x1bOk"


@pytest.mark.parametrize("mode", MODES)
def test_keypad_modifier_framing_and_numlock(mode):
    board, wire = driver(mode)
    board.feed_host_data("\x1b=".encode())
    board.input_key_event(KeyEvent("kp_1", KeyModifiers.CTRL))
    assert wire.text == ("\x1bOq" if mode in (1060, 1061) else "\x1bO5q")
    wire.data.clear()
    board.input_key_event(KeyEvent("kp_1", KeyModifiers.NUM_LOCK, text="1"))
    assert wire.text == "1"
    wire.data.clear()
    board.feed_host_data("\x1b[?1035l".encode())
    board.input_key_event(KeyEvent("kp_1", KeyModifiers.NUM_LOCK, text="1"))
    assert wire.text == "\x1bOq"


@pytest.mark.parametrize("mode", MODES)
def test_kitty_precedence_and_release_suppression(mode):
    board, wire = driver(mode)
    board.input_key_event(KeyEvent("f1", event_type="release"))
    assert not wire.data
    board.feed_host_data("\x1b[>31u".encode())
    board.input_key_event(KeyEvent("f1", KeyModifiers.SHIFT))
    board.input_key_event(KeyEvent("kp_add"))
    assert wire.text == "\x1b[1;2P\x1b[57413u"
    wire.data.clear()
    board.feed_host_data("\x1b[<u".encode())
    board.input_key_event(KeyEvent("f1"))
    assert wire.text != "\x1b[1;2P"


@pytest.mark.parametrize(
    "model,supported",
    [(BITTTY, set(MODES)), (XTERM, {1051, 1060, 1061}), (VT220, set()), (KITTY, set())],  # xterm 407: no HP or SCO
)
def test_model_repertoire(model, supported):
    board, _ = driver(1051, model)
    assert {mode for mode in MODES if board.modes.recognizes(True, mode)} == supported
    assert board.keyboard.style is (KeyboardStyle.SUN if supported else KeyboardStyle.DEFAULT)


def test_stdio_translates_known_outer_keys_without_changing_outer_protocol():
    terminal = StdioTerminal()
    wire = MemoryConnection()
    terminal.board.host.attach(wire)
    terminal.board.feed_host_data("\x1b[?1052h".encode())
    for part in (b"\x1b", b"O", b"P", b"\x1b", b"[", b"A"):
        terminal.handle_input(part)
    terminal.handle_input(b"\x1b[200~\x1bOP\x1b[A\x1b[201~")
    assert wire.text == "\x1bp\x1bA\x1bOP\x1b[A"
    assert terminal.host_keyboard_flags is None


# XTGETTCAP key strings reported by xterm 407 with each keyboard selected
# (this build omits HP and SCO), fed to the xterm profile.
@pytest.mark.parametrize(
    "mode,key,mods,expected",
    [
        (1051, "f1", KeyModifiers(0), "\x1b[224z"),  # kf1
        (1051, "f6", KeyModifiers(0), "\x1b[229z"),  # kf6
        (1051, "f9", KeyModifiers(0), "\x1b[232z"),  # kf9
        (1051, "f13", KeyModifiers(0), "\x1b[194z"),  # kf13
        (1051, "up", KeyModifiers(0), "\x1bOA"),  # kcuu1
        (1051, "home", KeyModifiers(0), "\x1b[214z"),  # khome
        (1051, "end", KeyModifiers(0), "\x1b[220z"),  # kend
        (1051, "insert", KeyModifiers(0), "\x1b[2z"),  # kich1
        (1051, "pageup", KeyModifiers(0), "\x1b[216z"),  # kpp
        (1051, "pagedown", KeyModifiers(0), "\x1b[222z"),  # knp
        (1051, "up", KeyModifiers.SHIFT, "\x1b[1;2A"),  # kUP
        (1051, "home", KeyModifiers.SHIFT, "\x1b[214;2z"),  # kHOM
        (1060, "f1", KeyModifiers(0), "\x1b[11~"),  # kf1
        (1060, "f6", KeyModifiers(0), "\x1b[17~"),  # kf6
        (1060, "f9", KeyModifiers(0), "\x1b[20~"),  # kf9
        (1060, "f13", KeyModifiers(0), "\x1b[25~"),  # kf13
        (1060, "up", KeyModifiers(0), "\x1b[A"),  # kcuu1
        (1060, "home", KeyModifiers(0), "\x1b[H"),  # khome
        (1060, "end", KeyModifiers(0), "\x1b[F"),  # kend
        (1060, "insert", KeyModifiers(0), "\x1b[2~"),  # kich1
        (1060, "pageup", KeyModifiers(0), "\x1b[5~"),  # kpp
        (1060, "pagedown", KeyModifiers(0), "\x1b[6~"),  # knp
        (1060, "up", KeyModifiers.SHIFT, "\x1b[A"),  # kUP
        (1060, "home", KeyModifiers.SHIFT, "\x1b[H"),  # kHOM
        (1061, "f1", KeyModifiers(0), "\x1bOP"),  # kf1
        (1061, "f6", KeyModifiers(0), "\x1b[17~"),  # kf6
        (1061, "f9", KeyModifiers(0), "\x1b[20~"),  # kf9
        (1061, "f13", KeyModifiers(0), "\x1b[25~"),  # kf13
        (1061, "up", KeyModifiers(0), "\x1b[A"),  # kcuu1
        (1061, "home", KeyModifiers(0), "\x1b[1~"),  # khome
        (1061, "end", KeyModifiers(0), "\x1b[4~"),  # kend
        (1061, "insert", KeyModifiers(0), "\x1b[2~"),  # kich1
        (1061, "pageup", KeyModifiers(0), "\x1b[5~"),  # kpp
        (1061, "pagedown", KeyModifiers(0), "\x1b[6~"),  # knp
    ],
)
def test_xterm_reports_the_same_key_strings(mode, key, mods, expected):
    board, wire = driver(mode, XTERM)
    board.input_key_event(KeyEvent(key, mods))
    assert wire.text == expected
