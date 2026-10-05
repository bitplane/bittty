"""Keymap wire fixtures, captured from real terminals (xterm 407 via XTEST, tmux 3.6 via send-keys)."""

import pytest

from bittty import Board, KeyEvent, KeyModifiers
from bittty.connections import MemoryConnection
from bittty.model import BITTTY, KITTY, LINUX, SCREEN, TMUX, VT100, VT220, XTERM

M = KeyModifiers


def driver(model=XTERM, setup=""):
    board = Board(model=model)
    wire = MemoryConnection()
    board.host.attach(wire)
    board.feed_host_data(setup.encode())
    return board, wire


@pytest.mark.parametrize(
    "setup,event,expected",
    [
        ("", KeyEvent("f13"), "\x1b[25~"),
        ("", KeyEvent("f20", M.SHIFT), "\x1b[34;2~"),
        ("", KeyEvent("f35"), "\x1b[56~"),
        ("", KeyEvent("find"), "\x1b[1~"),
        ("", KeyEvent("select", M.CTRL), "\x1b[4;5~"),
        ("", KeyEvent("help"), "\x1b[28~"),
        ("", KeyEvent("menu"), "\x1b[29~"),
        ("", KeyEvent("begin"), "\x1b[E"),
        ("", KeyEvent("kp_begin"), "\x1b[E"),
        ("\x1b[?1h", KeyEvent("home"), "\x1bOH"),
        ("\x1b[?1h", KeyEvent("end"), "\x1bOF"),
        ("\x1b[?1h", KeyEvent("kp_home"), "\x1bOH"),
        ("\x1b[?1h", KeyEvent("kp_begin"), "\x1bOE"),
        ("\x1b[?1h", KeyEvent("home", M.CTRL), "\x1b[1;5H"),
        ("\x1b=", KeyEvent("kp_equal"), "\x1bOX"),
        ("\x1b=", KeyEvent("kp_separator"), "\x1bOl"),
        ("\x1b=", KeyEvent("kp_enter", M.CTRL), "\x1bO5M"),
        ("\x1b=", KeyEvent("kp_add", M.ALT), "\x1bO3k"),
        ("", KeyEvent("kp_divide", M.CTRL, text="/"), "/"),
        ("\x1b[>4;2m", KeyEvent("kp_1", M.CTRL, text="1"), "1"),
        # NumLock (mode 1035, set by default) keeps the keypad numeric under DECKPAM.
        ("\x1b=", KeyEvent("kp_1", M.NUM_LOCK, text="1"), "1"),
        ("\x1b=", KeyEvent("kp_1", M.NUM_LOCK | M.CTRL, text="1"), "1"),
        ("\x1b=\x1b[?1035l", KeyEvent("kp_1", M.NUM_LOCK, text="1"), "\x1bOq"),
    ],
)
def test_xterm_default_keyboard(setup, event, expected):
    board, wire = driver(setup=setup)
    board.input_key_event(event)
    assert wire.text == expected


@pytest.mark.parametrize(
    "key,modifier,expected",
    [("pf1", 1, "\x1bOP"), ("pf4", 1, "\x1bOS"), ("pf1", 2, "\x1bO2P"), ("pf2", 5, "\x1bO5Q")],
)
def test_xterm_pf_keys_keep_modifiers_inside_ss3(key, modifier, expected):
    board, wire = driver()
    board.input_key(key, modifier)
    assert wire.text == expected


@pytest.mark.parametrize("key,expected", [("Tab", "\t"), ("Space", " "), ("Enter", "\r"), ("=", "="), (",", ",")])
def test_numeric_keypad_sends_its_text(key, expected):
    board, wire = driver()
    board.input_numpad_key(key)
    assert wire.text == expected


@pytest.mark.parametrize("model", [VT100, VT220, LINUX, SCREEN])
@pytest.mark.parametrize("key,expected", [(",", "\x1bOl"), ("=", "\x1bOX"), ("Tab", "\x1bOI")])
def test_application_keypad_is_shared(model, key, expected):
    board, wire = driver(model, "\x1b=")
    board.input_numpad_key(key)
    assert wire.text == expected


def test_numlock_does_not_override_deckpam_without_mode_1035():
    board, wire = driver(LINUX, "\x1b=")
    board.input_key_event(KeyEvent("kp_1", M.NUM_LOCK, text="1"))
    assert wire.text == "\x1bOq"


@pytest.mark.parametrize("model", [VT100, VT220])
@pytest.mark.parametrize("key,expected", [("pf1", "\x1bOP"), ("pf2", "\x1bOQ"), ("pf3", "\x1bOR"), ("pf4", "\x1bOS")])
def test_dec_pf_keys(model, key, expected):
    board, wire = driver(model)
    board.input_key(key)
    assert wire.text == expected


@pytest.mark.parametrize(
    "key,expected", [("find", "\x1b[1~"), ("select", "\x1b[4~"), ("help", "\x1b[28~"), ("menu", "\x1b[29~")]
)
def test_vt220_editing_and_help_do_keys(key, expected):
    board, wire = driver(VT220)
    board.input_key_event(KeyEvent(key))
    assert wire.text == expected


@pytest.mark.parametrize(
    "event,expected",
    [(KeyEvent("kp_0", M.SHIFT), "\x1bOp"), (KeyEvent("kp_enter", M.CTRL), "\x1bOM"), (KeyEvent("kp_0"), "\x1bOp")],
)
def test_tmux_application_keypad_carries_no_modifiers(event, expected):
    board, wire = driver(SCREEN, "\x1b=")
    board.input_key_event(event)
    assert wire.text == expected


@pytest.mark.parametrize("modifier", [0, 17, -1])
def test_legacy_modifier_outside_one_plus_mask_is_rejected(modifier):
    board, _ = driver()
    with pytest.raises(ValueError):
        board.input_key("up", modifier)
    with pytest.raises(ValueError):
        board.input_fkey(1, modifier)


@pytest.mark.parametrize("setup", ["\x1b[?1037h", "\x1b[?1060h"])
def test_delete_as_del_is_the_editing_keypad_delete_only(setup):
    """xterm 407: 1037 (and the legacy keyboard) make Delete DEL; KP_Delete stays CSI 3~."""
    board, wire = driver(setup=setup)
    board.input_key_event(KeyEvent("delete"))
    assert wire.text == "\x7f"
    wire.data.clear()
    board.input_key_event(KeyEvent("kp_delete"))
    assert wire.text == "\x1b[3~"


def test_sun_delete_ignores_modifiers_but_keypad_delete_does_not():
    """xterm 407, Sun function keys: Ctrl-Delete is CSI 3z, Ctrl-KP_Delete is CSI 3;5z."""
    board, wire = driver(setup="\x1b[?1051h\x1b[?1037h")
    board.input_key_event(KeyEvent("delete", M.CTRL))
    assert wire.text == "\x1b[3z"
    wire.data.clear()
    board.input_key_event(KeyEvent("kp_delete", M.CTRL))
    assert wire.text == "\x1b[3;5z"


def test_modified_delete_is_not_del_under_modify_other_keys():
    """xterm 407 with 1037: Delete and Ctrl-Delete are DEL, until modifyOtherKeys makes Ctrl-Delete CSI 3;5~."""
    board, wire = driver(setup="\x1b[?1037h")
    board.input_key_event(KeyEvent("delete", M.CTRL))
    assert wire.text == "\x7f"
    wire.data.clear()
    board.feed_host_data("\x1b[>4;1m".encode())
    board.input_key_event(KeyEvent("delete", M.CTRL))
    board.input_key_event(KeyEvent("delete"))
    assert wire.text == "\x1b[3;5~\x7f"


@pytest.mark.parametrize("setup", ["", "\x1b[?1051h", "\x1b[?1060h", "\x1b[?1061h", "\x1b[>4;1m"])
@pytest.mark.parametrize("mods", [M.SHIFT, M.SHIFT | M.CTRL])
def test_shift_tab_is_backtab(setup, mods):
    """xterm 407: Shift-Tab and Ctrl-Shift-Tab send CSI Z in every keyboard (modifyOtherKeys 2: see its tests)."""
    board, wire = driver(setup=setup)
    board.input_key_event(KeyEvent("tab", mods))
    assert wire.text == "\x1b[Z"


def test_vt220_has_no_backtab():
    board, wire = driver(VT220)
    board.input_key_event(KeyEvent("tab", M.SHIFT))
    assert wire.text == "\t"


@pytest.mark.parametrize(
    "setup,mods,expected",
    [("", M.NONE, "\x7f"), ("", M.CTRL, "\x08"), ("\x1b[?67h", M.NONE, "\x08"), ("\x1b[?67h", M.CTRL, "\x7f")],
)
def test_control_inverts_backarrow(setup, mods, expected):
    """xterm 407: Ctrl-Backspace sends whichever of BS/DEL Backspace does not."""
    board, wire = driver(setup=setup)
    board.input_key_event(KeyEvent("backspace", mods))
    assert wire.text == expected


def test_delete_mode_survives_ris_and_decstr():
    """xterm 407: 1037 is a setting, not terminal state; DECRQM shows the legacy keyboard's DEL default."""
    board, wire = driver(setup="\x1b[?1060h")
    board.feed_host_data("\x1b[?1037$p".encode())
    assert wire.text == "\x1b[?1037;1$y"
    board.feed_host_data("\x1b[?1037l\x1bc\x1b[!p".encode())
    wire.data.clear()
    board.input_key_event(KeyEvent("delete"))
    board.feed_host_data("\x1b[?1037$p".encode())
    assert wire.text == "\x1b[3~\x1b[?1037;2$y"


def test_sun_delete_takes_modifiers_under_modify_other_keys():
    board, wire = driver(setup="\x1b[?1051h\x1b[>4;1m")
    board.input_key_event(KeyEvent("delete", M.SHIFT))
    assert wire.text == "\x1b[3;2z"


@pytest.mark.parametrize(
    "setup,event,expected",
    [
        ("", KeyEvent("home"), "\x1b[1~"),
        ("", KeyEvent("home", M.CTRL), "\x1b[1;5H"),
        ("\x1b[?1h", KeyEvent("end", M.SHIFT), "\x1b[1;2F"),
        ("", KeyEvent("end", M.ALT | M.CTRL), "\x1b[1;7F"),
        ("", KeyEvent("up", M.ALT), "\x1b[1;3A"),
        ("", KeyEvent("a", M.ALT, text="a"), "\x1ba"),
        ("", KeyEvent("a", M.ALT | M.CTRL), "\x1b\x01"),
        ("", KeyEvent("enter", M.ALT), "\x1b\r"),
        ("", KeyEvent("escape", M.ALT), "\x1b\x1b"),
        ("", KeyEvent("backspace", M.ALT), "\x1b\x7f"),
        ("", KeyEvent("tab", M.ALT), "\x1b\t"),
        ("", KeyEvent("tab", M.SHIFT | M.ALT), "\x1b[Z"),
        ("", KeyEvent("kp_enter"), "\n"),
        ("", KeyEvent("kp_0", M.ALT, text="0"), "\x1b0"),
        ("\x1b=", KeyEvent("kp_0", M.ALT, text="0"), "\x1b\x1bOp"),
        ("\x1b=", KeyEvent("kp_enter", M.ALT), "\x1b\x1bOM"),
    ],
)
def test_tmux_keyboard(setup, event, expected):
    """tmux 3.6 via send-keys: xterm-style modified Home/End, Alt as an ESC prefix on text and keypad keys."""
    board, wire = driver(TMUX, setup)
    board.input_key_event(event)
    assert wire.text == expected


@pytest.mark.parametrize(
    "setup,event,expected",
    [
        ("\x1b[?1039h", KeyEvent("backspace", M.ALT), "\x1b\x7f"),
        ("\x1b[?1039h\x1b[?67h", KeyEvent("backspace", M.ALT), "\x1b\x08"),
        ("\x1b[?1039h", KeyEvent("backspace", M.ALT | M.CTRL), "\x1b\x08"),
    ],
)
def test_escape_prefix_applies_to_backspace(setup, event, expected):
    """xterm input.c: after the backarrow toggle Backspace is an ordinary one-byte key, so Alt/Meta prefix it."""
    board, wire = driver(setup=setup)
    board.input_key_event(event)
    assert wire.text == expected


@pytest.mark.parametrize(
    "setup,mods,expected",
    [
        ("", M.META, "\xe1"),
        ("", M.ALT, "\xe1"),
        ("", M.META | M.CTRL, "\x81"),
        ("\x1b[?1036h", M.META, "\x1ba"),
        ("\x1b[?1036h", M.ALT, "\xe1"),
        ("\x1b[?1039h", M.ALT, "\x1ba"),
        ("\x1b[?1039h", M.META, "\xe1"),
        ("\x1b[?1034l", M.META, "a"),
        ("\x1b[?1034l", M.ALT, "a"),
        ("\x1b[?1034l\x1b[?1039h", M.ALT, "\x1ba"),
    ],
)
def test_xterm_alt_and_meta_on_text_keys(setup, mods, expected):
    """xterm 407 in a UTF-8 locale (altIsNotMeta for Alt): ESC prefix if its mode is set, else the eighth
    bit while 1034 is set (its default), sent as a character; with neither, the modifier is dropped."""
    board, wire = driver(setup=setup)
    board.input_key_event(KeyEvent("a", mods, text="a"))
    assert wire.text == expected


def test_xterm_eighth_bit_backspace():
    board, wire = driver()
    board.input_key_event(KeyEvent("backspace", M.META))
    assert wire.text == "\xff"


def test_xterm_powers_on_with_eight_bit_input():
    board, wire = driver(setup="\x1b[?1034$p")
    assert wire.text == "\x1b[?1034;1$y"


@pytest.mark.parametrize("mods", [M.ALT, M.META])
def test_bittty_alt_and_meta_send_escape(mods):
    board, wire = driver(BITTTY)
    board.input_key_event(KeyEvent("a", mods, text="a"))
    board.feed_host_data("\x1bc".encode())
    board.input_key_event(KeyEvent("a", mods, text="a"))
    assert wire.text == "\x1ba\x1ba"


@pytest.mark.parametrize(
    "mods, expected",
    [(M.ALT, "\x1ba"), (M.ALT | M.SHIFT, "\x1bA"), (M.ALT | M.CTRL, "\x1b\x01")],
)
@pytest.mark.parametrize("model", [LINUX, KITTY], ids=["linux", "kitty"])
def test_alt_text_keys_send_escape_on_linux_and_kitty(model, mods, expected):
    """Linux keyboard.c powers on with VC_META (k_meta: ESC, key); kitty's legacy
    text keys "output the byte for ESC" when Alt is held. Neither can turn it off
    with a private mode, and RIS keeps it."""
    board, wire = driver(model)
    text = "A" if mods & M.SHIFT else "a"
    board.input_key_event(KeyEvent("a", mods, text=text, shifted_key="A"))
    board.feed_host_data("\x1bc\x1b[?1036l\x1b[?1039l".encode())
    board.input_key_event(KeyEvent("a", mods, text=text, shifted_key="A"))
    assert wire.text == expected * 2
