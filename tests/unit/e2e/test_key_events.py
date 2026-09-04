"""Wire-level tests for explicit keyboard facts and their policy interactions."""

import pytest

from bittty import VT220, Board, KeyEvent, MemoryConnection
from bittty import KeyModifiers as M
from bittty.present import Bell


def board_with_flags(flags=31, model=None):
    board = Board(width=10, height=2, **({"model": model} if model else {}))
    connection = MemoryConnection()
    board.host.attach(connection)
    board.parser.feed(f"\x1b[={flags}u")
    return board, connection


@pytest.mark.parametrize(
    "event,expected",
    [
        (KeyEvent("a", M.SHIFT, text="A", shifted_key="A"), "\x1b[97:65;2;65u"),
        (KeyEvent("с", M.CTRL, base_layout_key="c"), "\x1b[1089::99;5u"),
        (KeyEvent("a", M.SUPER), "\x1b[97;9u"),
        (KeyEvent("a", M.META), "\x1b[97;33u"),
        (KeyEvent("a", M.CAPS_LOCK | M.NUM_LOCK, text="A"), "\x1b[97;193;65u"),
        (KeyEvent("a", event_type="repeat", text="a"), "\x1b[97;1:2;97u"),
        (KeyEvent("a", event_type="release", text="a"), "\x1b[97;1:3u"),
        (KeyEvent("up", M.CTRL, "release"), "\x1b[1;5:3A"),
        (KeyEvent("delete", event_type="repeat"), "\x1b[3;1:2~"),
        (KeyEvent("f3"), "\x1b[13~"),
        (KeyEvent("f35", event_type="release"), "\x1b[57398;1:3u"),
        (KeyEvent("kp_1", text="1"), "\x1b[57400;;49u"),
        (KeyEvent("kp_enter", event_type="release"), "\x1b[57414;1:3u"),
        (KeyEvent("left_shift", M.SHIFT), "\x1b[57441;2u"),
        (KeyEvent("left_shift", event_type="release"), "\x1b[57441;1:3u"),
        (KeyEvent("e", text="e\u0301"), "\x1b[101;;101:769u"),
    ],
)
def test_full_protocol_events(event, expected):
    board, connection = board_with_flags()
    board.display.input_key_event(event)
    assert "".join(connection.data) == expected


@pytest.mark.parametrize("flags", [0, 1, 2, 3, 4, 5, 7, 16])
@pytest.mark.parametrize("key", ["a", "enter", "tab", "backspace"])
def test_release_escape_hatch(flags, key):
    board, connection = board_with_flags(flags)
    board.input_key_event(KeyEvent(key, event_type="release"))
    assert connection.data == []


def test_alternate_keys_do_not_force_encoding_or_guess_shift():
    board, connection = board_with_flags(4)
    board.input_key_event(KeyEvent("a", text="a", shifted_key="A"))
    board.parser.feed("\x1b[=13u")
    board.input_key_event(KeyEvent("a", shifted_key="A", base_layout_key="a"))
    assert "".join(connection.data) == "a\x1b[97::97u"


def test_event_types_alone_encode_nontext_repeat_and_release():
    board, connection = board_with_flags(2)
    board.input_key_event(KeyEvent("a", M.CTRL))
    board.input_key_event(KeyEvent("a", M.CTRL, "repeat"))
    board.input_key_event(KeyEvent("a", M.CTRL, "release"))
    assert "".join(connection.data) == "\x01\x1b[97;5:2u\x1b[97;5:3u"


def test_shift_tab_is_disambiguated_when_requested():
    board, connection = board_with_flags(1)
    board.input_key_event(KeyEvent("tab", M.SHIFT))
    assert "".join(connection.data) == "\x1b[9;2u"


@pytest.mark.parametrize(
    "flags,expected",
    [
        (0, "\x00"),
        (2, "\x1b[50;5:2u"),
        (3, "\x1b[57401;5:2u"),
        (31, "\x1b[57401;5:2u"),
    ],
)
def test_keypad_modifiers_and_independent_event_reporting(flags, expected):
    board, connection = board_with_flags(flags)
    board.parser.feed("\x1b[?66l")
    board.input_key_event(KeyEvent("kp_2", M.CTRL, "repeat"))
    assert "".join(connection.data) == expected


def test_release_has_no_local_echo_or_margin_bell():
    board, connection = board_with_flags()
    board.parser.feed("\x1b[12l\x1b[?44h")
    before = board.capture_text()
    events = []
    board.present = events.append
    board.cursor.x = 9
    board.input_key_event(KeyEvent("a", event_type="release", text="a"))
    assert board.capture_text() == before
    assert "".join(connection.data) == "\x1b[97;1:3u"
    assert not any(isinstance(event, Bell) for event in events)


def test_enhanced_enter_still_performs_local_echo():
    board, connection = board_with_flags()
    board.parser.feed("\x1b[12l")
    board.input_key_event(KeyEvent("a", text="a"))
    board.input_key_event(KeyEvent("enter"))
    assert board.cursor.y == 0  # Enter's local echo is CR, not an invented LF
    assert board.cursor.x == 0
    assert "".join(connection.data) == "\x1b[97;;97u\x1b[13u"


def test_all_flags_and_stacks_are_screen_local_and_reset():
    board, _ = board_with_flags(31)
    board.parser.feed("\x1b[>7u\x1b[?1049h")
    assert board.keyboard.kitty_flags == 0
    board.parser.feed("\x1b[>2u\x1b[?1049l\x1b[<u")
    assert board.keyboard.kitty_flags == 31
    board.parser.feed("\x1bc\x1b[?1049h")
    assert board.keyboard.kitty_flags == 0
    assert board.keyboard.kitty_stack == []


def test_super_is_not_silently_lost_before_negotiation():
    board, connection = board_with_flags(0)
    board.input_key_event(KeyEvent("a", M.SUPER))
    assert "".join(connection.data) == "\x1b[97;9u"


@pytest.mark.parametrize(
    "event,expected",
    [
        (KeyEvent("a", M.ALT | M.SHIFT, text="A"), "\x1bA"),
        (KeyEvent(" ", M.CTRL), "\x00"),
        (KeyEvent("[", M.CTRL), "\x1b"),
        (KeyEvent("ß", M.CTRL), "ß"),
        (KeyEvent("e", M.ALT, text="e\u0301"), "\x1be\u0301"),
    ],
)
def test_rich_events_preserve_legacy_text_and_control_mapping(event, expected):
    board, connection = board_with_flags(0)
    board.parser.feed("\x1b[?1039h")
    board.input_key_event(event)
    assert "".join(connection.data) == expected


def test_keyboard_lock_covers_events_and_committed_text():
    board, connection = board_with_flags()
    board.parser.feed("\x1b[2h")
    board.input_key_event(KeyEvent("a", text="a"))
    board.input_text("hello")
    assert connection.data == []


def test_legacy_model_gets_legacy_bytes_and_no_release():
    board, connection = board_with_flags(model=VT220)
    board.input_key_event(KeyEvent("a", M.CTRL))
    board.input_key_event(KeyEvent("a", M.CTRL, "repeat"))
    board.input_key_event(KeyEvent("a", M.CTRL, "release"))
    assert "".join(connection.data) == "\x01\x01"


def test_committed_text_and_paste_have_no_invented_keys():
    board, connection = board_with_flags()
    board.display.input_text("é🙂")
    board.display.input_paste("hello\n")
    assert "".join(connection.data) == "\x1b[0;;233:128578uhello\n"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"event_type": "unknown"},
        {"modifiers": 256},
        {"text": "\n"},
        {"text": "\ud800"},
        {"base_layout_key": "ab"},
        {"shifted_key": "\x1b"},
    ],
)
def test_invalid_frontend_facts_rejected(kwargs):
    with pytest.raises(ValueError):
        KeyEvent("a", **kwargs)
