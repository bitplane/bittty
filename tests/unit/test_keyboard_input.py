"""Outer input must survive arbitrary read boundaries without inventing keys."""

import pytest

from bittty import MemoryConnection
from bittty.terminals import StdioTerminal
from bittty.terminals.keyboard_input import MAX_SEQUENCE, decode_key


def terminal(flags=31, child_flags=31):
    term = StdioTerminal()
    connection = MemoryConnection()
    term.board.host.attach(connection)
    term.host_keyboard_flags = flags
    term.board.parser.feed(f"\x1b[={child_flags}u")
    return term, connection


@pytest.mark.parametrize("split", range(1, 26))
def test_explicit_key_survives_every_split(split):
    term, connection = terminal()
    sequence = b"\x1b[97:65:97;2:2;65u"
    term.handle_input(sequence[:split])
    term.flush_pending_input()  # must not truncate an incomplete CSI on idle
    term.handle_input(sequence[split:])
    assert "".join(connection.data) == sequence.decode()


def test_utf8_codepoints_survive_one_byte_reads():
    term, connection = terminal(flags=None, child_flags=0)
    for byte in "hello ❌🙂".encode():
        term.handle_input(bytes([byte]))
    assert "".join(connection.data) == "hello ❌🙂"


def test_rich_outer_events_encode_for_legacy_child():
    term, connection = terminal(child_flags=0)
    term.handle_input(b"\x1b[97;5u\x1b[97;5:3u\x1b[1;5A\x1b[13u")
    assert "".join(connection.data) == "\x01\x1b[1;5A\r"


def test_accepted_outer_flags_do_not_change_child_flags():
    term, connection = terminal(child_flags=1)
    term.host_keyboard_pushed = True
    term.handle_input(b"\x1b[?25u")
    assert term.host_keyboard_flags == 25
    assert term.board.keyboard.kitty_flags == 1
    assert connection.data == []


def test_replies_are_not_key_events_or_child_input():
    term, connection = terminal()
    term.handle_input("\x1b[1;5R\x1b[?62;1c\x1b[?31u\x1b[6;20;10t\x1b]11;rgb:11/22/33\x07")
    assert connection.data == []


def test_paste_is_one_streamed_transaction_and_does_not_parse_contents():
    term, connection = terminal()
    term.board.parser.feed("\x1b[?2004h")
    text = "ab\x1b[97;1:3u\x1b[O❌" * 1000
    payload = ("\x1b[200~" + text + "\x1b[201~").encode()
    for start in range(0, len(payload), 17):
        term.handle_input(payload[start : start + 17])
        assert len(term.input_parser.pending) <= 5
    assert "".join(connection.data) == "\x1b[200~" + text + "\x1b[201~"
    assert term.board.focused


def test_paste_markers_are_removed_for_legacy_child():
    term, connection = terminal(child_flags=0)
    term.handle_input("\x1b[200~a\x1b[A\n\x1b[201~")
    assert "".join(connection.data) == "a\x1b[A\n"


def test_oversized_unterminated_string_is_bounded_and_recovers():
    term, connection = terminal()
    term.handle_input("\x1b]" + "x" * (MAX_SEQUENCE * 20))
    assert len(term.input_parser.pending) <= MAX_SEQUENCE
    term.handle_input("\x07\x1b[97;;97u")
    assert "".join(connection.data) == "\x1b[97;;97u"


@pytest.mark.parametrize("raw", ["\x1b[97;999u", "\x1b[1114112u", "\x1b[97;1:4u", "\x1b[97;;10u"])
def test_invalid_wire_events_do_not_become_key_events(raw):
    assert decode_key(raw) is None


def test_committed_text_has_no_key_identity():
    term, connection = terminal()
    term.handle_input("\x1b[0;;233:128578u")
    assert "".join(connection.data) == "\x1b[0;;233:128578u"


def test_legacy_alt_prefix_and_unknown_escape_intermediates():
    term, connection = terminal(flags=None, child_flags=0)
    term.handle_input("\x1b[")
    term.flush_pending_input()
    for char in "\x1b(B":
        term.handle_input(char)
    assert "".join(connection.data) == "\x1b[\x1b(B"


def test_interrupted_sequence_does_not_swallow_later_key_reports():
    term, connection = terminal()
    term.handle_input("\x1b[97;\x1b[98;;98u")
    assert "".join(connection.data) == "\x1b[97;\x1b[98;;98u"
