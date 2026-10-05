"""Programmable key memory (VT510): DECPKA locks or restores the keys, DECRQPKFM reports free memory.

The VT510 reserves 804 bytes for programmed keys, shared by DECUDK. bittty has no Set-Up to save
definitions in, so recalling the saved definitions (DECPKA 3) recalls none, as does a factory reset.
"""

import pytest

from bittty import Board, KeyEvent, KeyModifiers, MemoryConnection
from bittty.model import BITTTY, LINUX, VT510, XTERM


def _run(sequence, model=VT510):
    board = Board(width=40, height=4, model=model)
    wire = MemoryConnection()
    board.host.attach(wire)
    board.feed_host_data(sequence.encode())
    return board, wire


def UDK(definitions, params="1;1"):
    return f"\x1bP{params}|{definitions}\x1b\\"


@pytest.mark.parametrize(
    ("sequence", "reply"),
    [
        ("", "\x1b[804;804+y"),
        (UDK("17/414243"), "\x1b[804;801+y"),
        (UDK("17/" + "41" * 800 + ";18/" + "42" * 5), "\x1b[804;4+y"),  # F7 did not fit
        (UDK("17/414243") + "\x1b[2+z", "\x1b[804;804+y"),  # factory defaults
        (UDK("17/414243") + "\x1b[3+z", "\x1b[804;804+y"),  # nothing saved to recall
        (UDK("17/414243") + "\x1b[1+z\x1b[2+z", "\x1b[804;801+y"),  # locked keys keep their definitions
    ],
)
def test_free_memory_report(sequence, reply):
    _, wire = _run(sequence + "\x1b[+x")
    assert wire.data == [reply]


def test_locking_stops_definitions():
    board, wire = _run("\x1b[1+z" + UDK("17/41") + "\x1b[?25n")
    assert board.keyboard.user_keys.keys == {}
    assert wire.data == ["\x1b[?21n"]


def test_no_action_does_nothing():
    board, _ = _run(UDK("17/41") + "\x1b[0+z\x1b[+z")
    board.input_key_event(KeyEvent("f6", KeyModifiers.SHIFT))
    assert board.keyboard.user_keys.keys == {6: b"A"}


def test_bittty_shares_the_vt510s_key_actions():
    _, wire = _run("\x1b[+x", BITTTY)
    assert wire.data == ["\x1b[4096;4096+y"]


@pytest.mark.parametrize("model", [XTERM, LINUX])
def test_terminals_without_programmable_keys_ignore_them(model):
    board, wire = _run("\x1b[1+z\x1b[+x", model)
    assert wire.data == [] and not board.keyboard.user_keys.locked
