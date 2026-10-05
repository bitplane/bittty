"""xterm key modifier resources: XTMODKEYS, XTQMODKEYS and XTFMTKEYS.

Fixtures captured from xterm 407 (XTEST key events).
"""

import pytest

from bittty import Board, KeyEvent, KeyModifiers
from bittty.connections import MemoryConnection
from bittty.model import LINUX, XTERM

M = KeyModifiers


def driver(setup="", model=XTERM):
    board = Board(model=model)
    wire = MemoryConnection()
    board.host.attach(wire)
    board.feed_host_data(setup.encode())
    wire.data.clear()
    return board, wire


def query(board, wire, resource):
    board.feed_host_data(f"\x1b[?{resource}m".encode())
    return "".join(wire.data.pop() for _ in list(wire.data))


@pytest.mark.parametrize(
    ("setup", "replies"),
    [
        ("", ["0;0", "1;2", "2;2", "3;0", "4;0", "5;0", "6;0", "7;0"]),
        (
            "\x1b[>0;1m\x1b[>1;3m\x1b[>2;0m\x1b[>3;1m\x1b[>4;2m",
            ["0;1", "1;3", "2;0", "3;1", "4;2", "5;0", "6;0", "7;0"],
        ),
        ("\x1b[>1;3m\x1b[>4;2m\x1b[>1m\x1b[>4m", ["0;0", "1;2", "2;2", "3;0", "4;0", "5;0", "6;0", "7;0"]),  # reset one
        ("\x1b[>1;3m\x1b[>4;2m\x1b[>m", ["0;0", "1;3", "2;2", "3;0", "4;2", "5;0", "6;0", "7;0"]),  # no reset-all
        ("\x1b[>1;9m", ["0;0", "1;9", "2;2", "3;0", "4;0", "5;0", "6;0", "7;0"]),  # stored as sent
        ("\x1b[>1;3m\x1b[>2;0m\x1b[>4;2m\x1b[!p", ["0;0", "1;2", "2;2", "3;0", "4;0", "5;0", "6;0", "7;0"]),  # DECSTR
        ("\x1b[>1;3m\x1b[>2;0m\x1b[>4;2m\x1bc", ["0;0", "1;2", "2;2", "3;0", "4;0", "5;0", "6;0", "7;0"]),  # RIS
    ],
)
def test_xtqmodkeys_reports_each_resource(setup, replies):
    board, wire = driver(setup)
    assert [query(board, wire, resource) for resource in range(8)] == [f"\x1b[>{reply}m" for reply in replies]


def test_xtqmodkeys_ignores_resources_xterm_does_not_have():
    board, wire = driver()
    assert query(board, wire, 8) == ""


def test_query_is_not_sgr_on_a_terminal_without_modifier_resources():
    board, wire = driver(model=LINUX)
    board.feed_host_data("\x1b[?4mX".encode())
    assert wire.data == []
    assert board.blitter.current_page.get_cell(0, 0)[0].underline is None


UP, END, F1, F5, F13 = "up", "end", "f1", "f5", "f13"


@pytest.mark.parametrize(
    ("setup", "key", "mods", "sent"),
    [
        # modifyCursorKeys
        ("\x1b[>1;0m", UP, M.SHIFT, "\x1b[2A"),
        ("\x1b[>1;0m", END, M.SHIFT, "\x1b[2F"),
        ("\x1b[>1;0m\x1b[?1h", UP, M.SHIFT, "\x1bO2A"),  # modifier first, SS3 kept
        ("\x1b[>1;1m\x1b[?1h", UP, M.SHIFT, "\x1b[2A"),  # modifier first, CSI prefix
        ("\x1b[>1;2m\x1b[?1h", UP, M.SHIFT, "\x1b[1;2A"),
        ("\x1b[>1;3m", UP, M.CTRL, "\x1b[>1;5A"),
        ("\x1b[>1;3m", END, M.SHIFT, "\x1b[>1;2F"),
        ("\x1b[>1;3m", "insert", M.CTRL, "\x1b[2;5~"),  # the editing keypad already has a parameter
        ("\x1b[>1;3m", UP, M.NONE, "\x1b[A"),
        ("\x1b[>1;4m", UP, M.SHIFT, "\x1b[27;2;57938~"),
        ("\x1b[>1;4m", UP, M.NONE, "\x1b[27;1;57938~"),
        ("\x1b[>1;4m", END, M.SHIFT, "\x1b[27;2;57943~"),
        ("\x1b[>1;4m", "insert", M.CTRL, "\x1b[27;5;57955~"),
        ("\x1b[>1;4m", "delete", M.SHIFT, "\x1b[27;2;127~"),
        ("\x1b[>1;4m", "find", M.SHIFT, "\x1b[27;2;57960~"),
        ("\x1b[>1;4m", F1, M.SHIFT, "\x1b[1;2P"),  # function keys follow their own resource
        ("\x1b[>1;9m", UP, M.NONE, "\x1b[27;1;57938~"),
        # modifyFunctionKeys
        ("\x1b[>2;0m", F1, M.SHIFT, "\x1bO2P"),
        ("\x1b[>2;0m", F5, M.SHIFT, "\x1b[15;2~"),
        ("\x1b[>2;1m", F1, M.CTRL, "\x1b[5P"),
        ("\x1b[>2;3m", F1, M.SHIFT, "\x1b[>1;2P"),
        ("\x1b[>2;3m", F13, M.CTRL, "\x1b[>25;5~"),
        ("\x1b[>2;3m", F5, M.NONE, "\x1b[15~"),
        ("\x1b[>2;4m", F1, M.NONE, "\x1b[27;1;58046~"),
        ("\x1b[>2;4m", F5, M.SHIFT, "\x1b[27;2;58050~"),
        ("\x1b[>2;4m", F13, M.CTRL, "\x1b[27;5;58058~"),
        ("\x1b[>2;4m", UP, M.SHIFT, "\x1b[1;2A"),
        # XTFMTKEYS: formatCursorKeys and formatFunctionKeys
        ("\x1b[>1;4m\x1b[>1;1f", UP, M.SHIFT, "\x1b[57938;2u"),
        ("\x1b[>2;4m\x1b[>2;1f", F5, M.SHIFT, "\x1b[58050;2u"),
        ("\x1b[>2;4m\x1b[>2;1f", F1, M.NONE, "\x1b[58046;1u"),
    ],
)
def test_modifier_resources_shape_special_keys(setup, key, mods, sent):
    board, wire = driver(setup)
    board.input_key_event(KeyEvent(key, mods))
    assert "".join(wire.data) == sent


@pytest.mark.parametrize(
    ("setup", "sent"),
    [
        ("\x1b[>4;2m", "\x1b[27;5;97~"),
        ("\x1b[>4;2m\x1b[>4;1f", "\x1b[97;5u"),  # formatOtherKeys
        ("\x1b[>4;2m\x1b[>4;1f\x1b[>4f", "\x1b[27;5;97~"),  # reset one
        ("\x1b[>4;2m\x1b[>4;1f\x1b[>f", "\x1b[97;5u"),  # no reset-all
        ("\x1b[>4;2m\x1b[>4;1f\x1b[!p\x1b[>4;2m", "\x1b[27;5;97~"),  # DECSTR restores the format
    ],
)
def test_format_other_keys(setup, sent):
    board, wire = driver(setup)
    board.input_key_event(KeyEvent("a", M.CTRL))
    assert "".join(wire.data) == sent


@pytest.mark.parametrize(
    ("event", "sent"),
    [
        (KeyEvent("a", M.ALT, text="a"), "\x1b[97;3u"),
        (KeyEvent("a", M.CTRL | M.SHIFT, shifted_key="A"), "\x1b[65;6u"),
        (KeyEvent("tab", M.CTRL), "\x1b[9;5u"),
        (KeyEvent("1", M.CTRL), "\x1b[49;5u"),
    ],
)
def test_format_other_keys_uses_csi_u(event, sent):
    board, wire = driver("\x1b[>4;2m\x1b[>4;1f")
    board.input_key_event(event)
    assert "".join(wire.data) == sent
