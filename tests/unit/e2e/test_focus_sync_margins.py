"""Focus events (1004), synchronized output (2026), left/right margins (69 + DECSLRM),
XTVERSION, the SGR/colour stacks, and DECBI/DECFI."""

from bittty import Board, MemoryConnection
from bittty.parser import Parser


def _term(width=10, height=4):
    board = Board(width=width, height=height)
    transport = MemoryConnection()
    board.host.attach(transport)
    return board, Parser(board), transport


def _sent(t):
    return "".join(t.data)


def _line(board, y=0):
    return board.blitter.current_page.get_line_text(y).rstrip()


# --- focus events (mode 1004) --- #


def test_focus_events_only_report_when_enabled():
    board, parser, transport = _term()
    board.focus_in()  # disabled by default -> nothing
    assert _sent(transport) == ""
    parser.feed("\x1b[?1004h")  # enable focus reporting
    board.focus_in()
    board.focus_out()
    assert _sent(transport) == "\x1b[I\x1b[O"


# --- synchronized output (mode 2026) --- #


def test_synchronized_output_flag_tracks_mode_2026():
    board, parser, _ = _term()
    assert board.modes.synchronized_output is False
    parser.feed("\x1b[?2026h")
    assert board.modes.synchronized_output is True
    parser.feed("\x1b[?2026l")
    assert board.modes.synchronized_output is False


def test_synchronized_output_reports_supported():
    _, parser, transport = _term()
    parser.feed("\x1b[?2026$p")
    assert transport.data[-1] == "\x1b[?2026;2$y"


# --- left/right margins (mode 69 DECLRMM + DECSLRM) --- #


def test_decslrm_needs_margin_mode_else_saves_cursor():
    board, parser, _ = _term()
    # Without DECLRMM, CSI Pl;Pr s is SCOSC (save cursor), not a margin set.
    board.cursor.set_position(3, 2)
    parser.feed("\x1b[2;6s")
    assert board.blitter.left_margin == 0  # unchanged
    board.cursor.set_position(0, 0)
    parser.feed("\x1b[u")  # restore -> the saved (3, 2)
    assert (board.cursor.x, board.cursor.y) == (3, 2)


def test_decslrm_sets_margins_when_mode_enabled():
    board, parser, _ = _term()
    parser.feed("\x1b[?69h")  # DECLRMM on
    parser.feed("\x1b[3;7s")  # margins to columns 3..7 (0-based 2..6)
    assert (board.blitter.left_margin, board.blitter.right_margin) == (2, 6)


def test_disabling_declrmm_resets_margins():
    board, parser, _ = _term()
    parser.feed("\x1b[?69h\x1b[3;7s")
    parser.feed("\x1b[?69l")  # disabling DECLRMM restores full width
    assert (board.blitter.left_margin, board.blitter.right_margin) == (0, 9)


def test_declrmm_reports_supported():
    _, parser, transport = _term()
    parser.feed("\x1b[?69$p")
    assert transport.data[-1] == "\x1b[?69;2$y"


def test_sl_pans_within_the_left_right_margins():
    board, parser, _ = _term()
    board.blitter.current_page.set(0, 0, "ABCDEFGHIJ")
    parser.feed("\x1b[?69h\x1b[3;6s")  # margins columns 3..6 (indices 2..5): C D E F
    parser.feed("\x1b[1 @")  # SL 1 — only cols 2..5 pan left: C D E F -> D E F <blank>
    assert _line(board) == "ABDEF GHIJ"  # index 5 blanked, cols outside margins untouched


# --- XTVERSION --- #


def test_xtversion_reports_name_and_version():
    board, parser, transport = _term()
    parser.feed("\x1b[>0q")
    reply = _sent(transport)
    assert reply.startswith("\x1bP>|bittty(") and reply.endswith("\x1b\\")


# --- SGR / colour stacks --- #


def test_xtpush_xtpop_sgr_restores_attributes():
    board, parser, _ = _term()
    parser.feed("\x1b[1;31m")  # bold red
    parser.feed("\x1b[#{")  # XTPUSHSGR
    parser.feed("\x1b[0m\x1b[34m")  # reset then blue
    parser.feed("\x1b[#}")  # XTPOPSGR -> back to bold red
    style = board.style.current
    assert style.bold is True
    assert style.fg is not None and style.fg.value == 1


def test_xtpush_xtpop_colors_restores_palette():
    board, parser, _ = _term()
    before = board.palette.colors[1]
    parser.feed("\x1b[#P")  # XTPUSHCOLORS
    parser.feed("\x1b]4;1;rgb:0102/0304/0506\x07")  # change palette entry 1
    assert board.palette.colors[1] != before
    parser.feed("\x1b[#Q")  # XTPOPCOLORS
    assert board.palette.colors[1] == before


# --- DECBI / DECFI --- #


def test_decfi_moves_right_but_stops_at_page_border():
    board, parser, _ = _term()
    board.cursor.set_position(4, 0)
    parser.feed("\x1b9")  # DECFI below the right margin -> just move right
    assert board.cursor.x == 5
    board.blitter.current_page.set(0, 0, "ABCDEFGHIJ")
    board.cursor.set_position(9, 0)
    parser.feed("\x1b9")  # the physical page border takes precedence over the margin
    assert _line(board) == "ABCDEFGHIJ"


def test_decbi_moves_left_but_stops_at_page_border():
    board, parser, _ = _term()
    board.cursor.set_position(3, 0)
    parser.feed("\x1b6")  # DECBI: not at left margin -> move left
    assert board.cursor.x == 2
    board.blitter.current_page.set(0, 0, "ABCDEFGHIJ")
    board.cursor.set_position(0, 0)
    parser.feed("\x1b6")  # the physical page border takes precedence over the margin
    assert _line(board) == "ABCDEFGHIJ"
