"""VT52 mode (DECANM reset): xterm's fifteen VT52 controls and keys, captured from xterm 407 (80x24)."""

import pytest

from bittty import Board, KeyEvent, KeyModifiers, MemoryConnection
from bittty.model import LINUX, XTERM

M = KeyModifiers
VT52 = "\x1b[?2l"


def Y(row, column):
    """ESC Y with one-based coordinates, each sent as value + 31."""
    return f"\x1bY{chr(31 + row)}{chr(31 + column)}"


def _run(sequence, model=XTERM):
    board = Board(width=80, height=24, model=model)
    wire = MemoryConnection()
    board.host.attach(wire)
    board.feed_host_data(sequence)
    return board, wire


def _screen(board, rows=3):
    lines = [board.blitter.current_page.get_line_text(y).rstrip() for y in range(rows)]
    return lines, (board.cursor.y + 1, board.cursor.display_x + 1)


@pytest.mark.parametrize(
    ("sequence", "lines", "cursor"),
    [
        (Y(3, 10) + "X", ["", "", "         X"], (3, 11)),
        (Y(3, 3) + Y(40, 10) + "X", ["", "", "         X"], (3, 11)),  # off-screen row: kept
        (Y(3, 3) + Y(2, 90) + "X", ["", "  X", ""], (2, 4)),  # off-screen column: kept
        ("\x1bA\x1bAX", ["X", "", ""], (1, 2)),  # no scrolling at the top
        ("\x1bB\x1bBX", ["", "", "X"], (3, 2)),
        ("\x1bC\x1bCX", ["  X", "", ""], (1, 4)),
        ("\x1bD\x1bDX", ["X", "", ""], (1, 2)),
        (Y(3, 5) + "\x1bHX", ["X", "", ""], (1, 2)),
        ("top\x1bH\x1bIX", ["X", "top", ""], (1, 2)),  # reverse line feed scrolls at the top
        (Y(3, 5) + "\x1bIX", ["", "    X", ""], (2, 6)),
        ("a" * 80 + "\x1bH\x1bC\x1bJ", ["a", "", ""], (1, 2)),
        ("a" * 80 + "\x1bH\x1bC\x1bK", ["a", "", ""], (1, 2)),
        ("\x1bFlqk\x1bGlqk", ["⎺⎼↓lqk", "", ""], (1, 7)),  # the VT52 graphics set
        ("\x1b[5CX", ["5CX", "", ""], (1, 4)),  # no CSI: ESC [ is an unknown VT52 control
        ("\x1bQX\x1b1Y", ["XY", "", ""], (1, 3)),  # unknown controls are ignored
        ("\x1b7" + Y(3, 3) + "\x1b8X", ["", "", "  X"], (3, 4)),  # ...DECSC and DECRC among them
        ("abc\x1bcX", ["abcX", "", ""], (1, 5)),  # ...and RIS
        ("ab\rc\tde\x08f\ng", ["cb      df", "          g", ""], (2, 12)),
        ("a\x07b", ["ab", "", ""], (1, 3)),
        (Y(1, 79) + "abc", [" " * 78 + "ac", "", ""], (1, 80)),  # no autowrap
    ],
)
def test_vt52_controls(sequence, lines, cursor):
    board, _ = _run(VT52 + sequence)
    assert _screen(board) == (lines, cursor)


def test_there_are_no_locking_shifts():
    board, _ = _run("\x1b)0" + VT52 + "\x0elq\x0f")
    assert _screen(board) == (["lq", "", ""], (1, 3))


def test_the_scroll_region_still_applies():
    board, _ = _run("\x1b[5;10r" + VT52 + Y(10, 1) + "\n\nX")
    assert _screen(board, 10)[0][9] == "X"


def test_vt52_graphics_characters():
    board, _ = _run(VT52 + "\x1bF" + "".join(chr(c) for c in range(0x5E, 0x7F)))
    assert board.blitter.current_page.get_line_text(0).rstrip() == "^  ▮⅟   °±→…÷↓⎺⎺⎻⎻⎼⎼⎽⎽₀₁₂₃₄₅₆₇₈₉¶"


def test_identify():
    board, wire = _run(VT52 + "\x1bZ")
    assert wire.data == ["\x1b/Z"]


def test_esc_less_than_returns_to_ansi_and_restores_the_charsets():
    """VT52 starts in ASCII whatever G0 was; ESC < brings G0 back (and leaves VT52 graphics behind)."""
    board, wire = _run("\x1b(0" + VT52 + "x\x1bF\x1b<q\x1b[?2$p")
    assert board.blitter.current_page.get_line_text(0).rstrip() == "x─"
    assert wire.data == ["\x1b[?2;1$y"]


def test_decrqm_reports_vt52_mode_only_after_leaving_it():
    board, wire = _run(VT52 + "\x1b[?2$p")
    assert wire.data == []


@pytest.mark.parametrize(("setup", "keypad"), [("\x1b=", True), ("\x1b=\x1b>", False)])
def test_keypad_mode_controls(setup, keypad):
    board, _ = _run(VT52 + setup)
    assert board.modes.application_keypad is keypad


@pytest.mark.parametrize(
    ("setup", "event", "sent"),
    [
        ("", KeyEvent("up"), "\x1bA"),
        ("", KeyEvent("down"), "\x1bB"),
        ("", KeyEvent("right"), "\x1bC"),
        ("", KeyEvent("left"), "\x1bD"),
        ("", KeyEvent("home"), "\x1bH"),
        ("", KeyEvent("end"), "\x1bF"),
        ("", KeyEvent("f1"), "\x1bP"),
        ("", KeyEvent("f2"), "\x1bQ"),
        ("", KeyEvent("pf1"), "\x1bP"),
        ("", KeyEvent("f5"), "\x1b[15~"),  # xterm keeps its own keys beyond VT52's
        ("", KeyEvent("insert"), "\x1b[2~"),
        ("", KeyEvent("up", M.SHIFT), "\x1bA"),  # no modifiers
        ("", KeyEvent("f1", M.CTRL), "\x1bP"),
        ("\x1b[?1h", KeyEvent("up"), "\x1bA"),  # DECCKM has no VT52 form
        ("\x1b=", KeyEvent("kp_enter"), "\x1b?M"),
        ("\x1b=", KeyEvent("kp_add"), "\x1b?k"),
        ("\x1b=", KeyEvent("kp_decimal"), "\x1b?n"),
        ("\x1b=", KeyEvent("kp_multiply"), "\x1b?j"),
        ("\x1b=", KeyEvent("kp_subtract"), "\x1b?m"),
    ],
)
def test_vt52_keys(setup, event, sent):
    board, wire = _run(VT52 + setup)
    board.input_key_event(event)
    assert wire.text == sent


def test_a_terminal_without_vt52_mode_stays_ansi():
    board, _ = _run(VT52 + "\x1bAx\x1b[2CX", model=LINUX)
    assert board.blitter.current_page.get_line_text(0).rstrip() == "x  X"
