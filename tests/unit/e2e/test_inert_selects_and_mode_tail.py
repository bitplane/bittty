"""Inert-select cluster (raw 8-bit C1, SPA/EPA, S7C1T/S8C1T, ANSI level) + the mode tail."""

from bittty.parser import Parser
from bittty import Board


def _term(width=10, height=3):
    board = Board(width=width, height=height)
    return board, Parser(board)


# --- raw 8-bit C1 format controls --- #


def test_raw_8bit_c1_index_and_reverse_index():
    board, parser = _term()
    board.cursor.set_position(0, 1)
    parser.feed("\x84")  # IND (8-bit) — line feed
    assert board.cursor.y == 2
    parser.feed("\x8d")  # RI (8-bit) — reverse index
    assert board.cursor.y == 1


def test_raw_8bit_c1_hts_sets_tab_stop():
    board, parser = _term(width=20)
    board.cursor.set_position(5, 0)
    parser.feed("\x88")  # HTS (8-bit)
    board.cursor.set_position(0, 0)
    parser.feed("\t")
    assert board.cursor.x == 5


# --- SPA / EPA protected area --- #


def test_spa_epa_toggle_protection():
    board, parser = _term()
    parser.feed("\x1bV")  # SPA (ESC V) — start protected area
    assert board.style.current.protected is True
    parser.feed("\x1bW")  # EPA (ESC W) — end protected area
    assert board.style.current.protected is None


def test_spa_8bit_form():
    board, parser = _term()
    parser.feed("\x96")  # SPA (8-bit)
    assert board.style.current.protected is True


# --- S7C1T / S8C1T and ANSI conformance --- #


def test_c1_transmission_select():
    board, parser = _term()
    parser.feed("\x1b G")  # ESC SP G — S8C1T
    assert board.c1_eightbit is True
    parser.feed("\x1b F")  # ESC SP F — S7C1T
    assert board.c1_eightbit is False


def test_ansi_conformance_level():
    board, parser = _term()
    parser.feed("\x1b M")  # ESC SP M — ANSI conformance level 2
    assert board.ansi_conformance_level == 2
    parser.feed("\x1b L")  # ESC SP L — level 1
    assert board.ansi_conformance_level == 1


# --- mode tail --- #


def test_mode_tail_flags_store_and_report():
    board, parser = _term()
    modes = board.modes
    parser.feed("\x1b[?1010h")  # scroll on output
    parser.feed("\x1b[?1037h")  # delete sends DEL
    assert modes.scroll_on_output is True
    assert modes.delete_sends_del is True


def test_mode_tail_defaults():
    board, _ = _term()
    modes = board.modes
    # xterm-default-on flags
    assert modes.special_modifiers is True
    assert modes.sixel_private_registers is True
    # default-off
    assert modes.scroll_on_keypress is False


def test_mode_tail_reports_via_decrqm():
    board, parser = _term()

    class Rec:
        def __init__(self):
            self.data = []

        def write(self, d):
            self.data.append(d)

        def flush(self):
            pass

    rec = Rec()
    board.host.attach(rec)
    parser.feed("\x1b[?1035$p")  # special_modifiers, default on
    assert rec.data[-1] == "\x1b[?1035;1$y"
    parser.feed("\x1b[?1010$p")  # scroll_on_output, default off
    assert rec.data[-1] == "\x1b[?1010;2$y"
