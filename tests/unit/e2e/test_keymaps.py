"""Keymap wire fixtures, captured from real terminals (xterm 407 via XTEST, tmux 3.6 via send-keys)."""

import pytest

from bittty import Board, KeyEvent, KeyModifiers
from bittty.connections import MemoryConnection
from bittty.model import LINUX, SCREEN, VT100, VT220, XTERM

M = KeyModifiers


def driver(model=XTERM, setup=""):
    board = Board(model=model)
    wire = MemoryConnection()
    board.host.attach(wire)
    board.feed_host_data(setup)
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
