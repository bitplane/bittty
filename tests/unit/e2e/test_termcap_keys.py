"""xterm's terminfo/termcap function-key mode (1050): unmodified keys send the strings of xterm's
terminfo entry, and modified keys what they otherwise would. Captured from xterm 407.
"""

import pytest

from bittty import Board, KeyEvent, KeyModifiers, MemoryConnection
from bittty.model import BITTTY, VT510, XTERM

M = KeyModifiers
CSI, SS3 = "\x1b[", "\x1bO"

TERMCAP = {
    "up": SS3 + "A",
    "down": SS3 + "B",
    "left": SS3 + "D",
    "right": SS3 + "C",
    "home": SS3 + "H",
    "end": SS3 + "F",
    **{f"f{n}": CSI + f"1;2{final}" for n, final in zip(range(13, 17), "PQRS")},
    **{f"f{n}": CSI + f"{code};2~" for n, code in zip(range(17, 25), (15, 17, 18, 19, 20, 21, 23, 24))},
    **{f"f{n}": CSI + f"1;5{final}" for n, final in zip(range(25, 29), "PQRS")},
    **{f"f{n}": CSI + f"{code};5~" for n, code in zip(range(29, 36), (15, 17, 18, 19, 20, 21, 23))},
    "kp_enter": SS3 + "M",
}


def _key(event, setup="\x1b[?1050h", model=XTERM):
    board = Board(model=model)
    wire = MemoryConnection()
    board.host.attach(wire)
    board.feed_host_data(setup)
    board.input_key_event(event)
    return wire.text


@pytest.mark.parametrize(("key", "sent"), TERMCAP.items())
def test_unmodified_keys_send_terminfo_strings(key, sent):
    assert _key(KeyEvent(key)) == sent


@pytest.mark.parametrize(
    ("event", "sent"),
    [
        (KeyEvent("up", M.SHIFT), CSI + "1;2A"),
        (KeyEvent("home", M.CTRL), CSI + "1;5H"),
        (KeyEvent("f13", M.SHIFT), CSI + "25;2~"),
        (KeyEvent("kp_enter", M.SHIFT), "\r"),
        (KeyEvent("kp_enter", M.CTRL), "\r"),
        (KeyEvent("f1"), SS3 + "P"),  # keys terminfo agrees on are unchanged
        (KeyEvent("pageup"), CSI + "5~"),
    ],
)
def test_other_keys_are_as_ever(event, sent):
    assert _key(event) == sent


def test_reset_restores_the_default_keys():
    assert _key(KeyEvent("up"), "\x1b[?1050h\x1b[?1050l") == CSI + "A"


def test_decrqm():
    board = Board(model=XTERM)
    wire = MemoryConnection()
    board.host.attach(wire)
    board.feed_host_data("\x1b[?1050$p\x1b[?1050h\x1b[?1050$p")
    assert wire.data == ["\x1b[?1050;2$y", "\x1b[?1050;1$y"]


@pytest.mark.parametrize(("model", "sent"), [(BITTTY, SS3 + "A"), (VT510, CSI + "A")])
def test_availability(model, sent):
    assert _key(KeyEvent("up"), model=model) == sent
