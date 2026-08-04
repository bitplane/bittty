"""Streaming extended-grapheme handling under DEC private mode 2027."""

import pytest

from bittty import Board
from bittty.video import WideHead


def clustered_board(*, width=12, height=3):
    board = Board(width=width, height=height)
    board.parser.feed("\x1b[?2027h")
    return board


def cells(board, y=0):
    return [cell[1] for cell in board.blitter.current_page.grid[y]]


def snapshot(board):
    return (
        [[(style, str(char), type(char)) for style, char in row] for row in board.get_content()],
        (board.cursor.x, board.cursor.y),
        board.capture_text(),
    )


def test_mode_off_preserves_legacy_codepoint_writes():
    board = Board(width=5, height=1)
    board.parser.feed("e\u0301")

    assert cells(board)[:2] == ["e", "\u0301"]
    assert board.cursor.x == 2


@pytest.mark.parametrize(
    "text, expected_width",
    [
        ("e\u0301", 1),
        ("🧑\u200d🌾", 2),
        ("🇬🇧", 2),
        ("1\ufe0f\u20e3", 2),
        ("☀\ufe0f", 2),
        ("☀\ufe0e", 1),
        ("각", 2),
        ("क्\u0937ि", 2),
        ("\u0600A", 2),
    ],
)
def test_every_codepoint_split_matches_one_shot(text, expected_width):
    whole = clustered_board()
    whole.parser.feed(text)
    expected = snapshot(whole)

    for split in range(1, len(text)):
        streamed = clustered_board()
        streamed.parser.feed(text[:split])
        streamed.parser.feed(text[split:])
        assert snapshot(streamed) == expected

    assert whole.cursor.x == expected_width


def test_cluster_is_stored_once_with_a_structural_wide_marker():
    board = clustered_board()
    board.parser.feed("🧑")
    board.parser.feed("\u200d🌾")

    assert cells(board)[:2] == ["🧑\u200d🌾", ""]
    assert isinstance(cells(board)[0], WideHead)
    assert board.capture_pane().count("🧑\u200d🌾") == 1


def test_safe_style_change_does_not_split_or_restyle_cluster():
    board = clustered_board()
    board.parser.feed("\x1b[31me\x1b[34m\u0301")

    head = board.blitter.current_page.get_cell(0, 0)
    assert head[1] == "e\u0301"
    assert head[0].fg.mode == "indexed"
    assert head[0].fg.value == 1


def test_cursor_movement_invalidates_the_streaming_tail():
    board = clustered_board()
    board.parser.feed("e\x1b[C\u0301")

    assert cells(board)[:3] == ["e", " ", " "]
    assert board.cursor.x == 2


def test_orphan_zero_width_mark_is_ignored():
    board = clustered_board()
    board.parser.feed("\u0301A")

    assert cells(board)[:2] == ["A", " "]
    assert board.cursor.x == 1


def test_split_prepend_sequence_waits_for_its_base():
    board = clustered_board()
    board.parser.feed("\u0600")
    assert board.cursor.x == 0
    board.parser.feed("A")

    assert cells(board)[:2] == ["\u0600A", ""]
    assert board.cursor.x == 2


def test_width_growth_in_final_column_relocates_before_wrapping():
    board = clustered_board(width=4, height=2)
    board.cursor.x = 3
    board.parser.feed("☀")
    board.parser.feed("\ufe0f")

    assert cells(board, 0) == [" "] * 4
    assert cells(board, 1)[:2] == ["☀\ufe0f", ""]
    assert (board.cursor.x, board.cursor.y) == (2, 1)


def test_width_growth_without_autowrap_backs_up():
    board = clustered_board(width=4, height=2)
    board.modes.auto_wrap = False
    board.cursor.x = 3
    board.parser.feed("☀")
    board.parser.feed("\ufe0f")

    assert cells(board, 0)[2:] == ["☀\ufe0f", ""]
    assert (board.cursor.x, board.cursor.y) == (3, 0)


def test_width_shrink_releases_continuation_and_cancels_delayed_wrap():
    board = clustered_board(width=4, height=2)
    board.cursor.x = 2
    board.parser.feed("⌚")
    assert board.cursor.x == 4
    board.parser.feed("\ufe0e")

    assert cells(board, 0)[2:] == ["⌚\ufe0e", " "]
    assert board.cursor.x == 3


def test_insert_mode_streaming_matches_one_shot():
    text = "1\ufe0f\u20e3"

    whole = clustered_board(width=8, height=1)
    whole.parser.feed("abcdef")
    whole.cursor.x = 2
    whole.modes.insert_mode = True
    whole.parser.feed(text)

    streamed = clustered_board(width=8, height=1)
    streamed.parser.feed("abcdef")
    streamed.cursor.x = 2
    streamed.modes.insert_mode = True
    for char in text:
        streamed.parser.feed(char)

    assert snapshot(streamed) == snapshot(whole)


@pytest.mark.parametrize("auto_wrap", [False, True])
def test_insert_mode_final_column_growth_restores_speculative_write(auto_wrap):
    def render(parts):
        board = clustered_board(width=6, height=2)
        board.parser.feed("abcdef")
        board.cursor.x = 5
        board.modes.insert_mode = True
        board.modes.auto_wrap = auto_wrap
        for part in parts:
            board.parser.feed(part)
        return snapshot(board)

    assert render(["☀", "\ufe0f"]) == render(["☀\ufe0f"])


@pytest.mark.parametrize("insert_mode", [False, True])
def test_width_shrink_over_content_matches_one_shot(insert_mode):
    def render(parts):
        board = clustered_board(width=8, height=1)
        board.parser.feed("abcdefgh")
        board.cursor.x = 2
        board.modes.insert_mode = insert_mode
        for part in parts:
            board.parser.feed(part)
        return snapshot(board)

    assert render(["⌚", "\ufe0e"]) == render(["⌚\ufe0e"])


def test_rep_repeats_the_complete_cluster():
    board = clustered_board(width=10, height=1)
    board.parser.feed("e\u0301\x1b[3b")

    assert board.capture_text() == "e\u0301" * 4
    assert board.cursor.x == 4


def test_cluster_growth_is_capped_and_next_boundary_recovers():
    board = clustered_board(width=5, height=1)
    board.parser.feed("A")
    for _ in range(300):
        board.parser.feed("\u0301")
    board.parser.feed("B")

    assert len(cells(board)[0]) == 256
    assert cells(board)[1] == "B"
    assert board.cursor.x == 2


def test_mode_change_and_reset_discard_pending_assembly():
    board = clustered_board(width=5, height=1)
    board.parser.feed("e\x1b[?2027l\u0301")
    assert cells(board)[:2] == ["e", "\u0301"]

    board.parser.feed("\x1b[?2027h\u0600\x1b[!pA")
    assert cells(board)[0] == "A"


# --- insert mode (IRM) under clustering --- #


def test_insert_mode_shifts_existing_content_for_an_ascii_run():
    """Clustering has its own insert-mode path, separate from the plain writer."""
    board = clustered_board(width=12, height=1)
    board.parser.feed("ABCDEFGH")
    board.parser.feed("\x1b[1;1H\x1b[4h")  # home, IRM on

    board.parser.feed("xyz")

    assert board.capture_text() == "xyzABCDEFGH"
    assert board.cursor.x == 3


def test_insert_mode_run_ending_in_a_cluster_still_assembles_it():
    """The last character of an inserted run stays a speculation candidate."""
    board = clustered_board(width=12, height=1)
    board.parser.feed("ABCDEFGH")
    board.parser.feed("\x1b[1;1H\x1b[4h")

    board.parser.feed("xye")
    board.parser.feed("́")  # the combining mark arrives in the next chunk

    assert board.capture_text() == "xýABCDEFGH".replace("ý", "yé")
    assert cells(board)[2] == "é"
    assert board.cursor.x == 3


# --- oversized clusters --- #


def test_oversized_cluster_arriving_whole_is_truncated_and_flagged():
    """A >256-codepoint cluster in a single chunk, not assembled one mark at a time.

    The incremental route is covered by test_cluster_growth_is_capped_...; this is
    the other entry, where the whole ZWJ bomb lands inside one write.
    """
    board = clustered_board(width=8, height=1)

    board.parser.feed("a" + "́" * 300)
    assert len(cells(board)[0]) == 256
    assert board.cursor.x == 1

    # Overflow keeps a tail of context so later marks still join this cluster
    # rather than starting a fresh one in the next cell.
    board.parser.feed("́" * 5)
    assert len(cells(board)[0]) == 256
    assert cells(board)[1] == " "
    assert board.cursor.x == 1


def test_oversized_cluster_still_ends_at_the_next_boundary():
    """Overflow must not swallow whatever follows it."""
    board = clustered_board(width=8, height=1)

    board.parser.feed("a" + "́" * 300 + "B")

    assert len(cells(board)[0]) == 256
    assert cells(board)[1] == "B"
    assert board.cursor.x == 2


# --- speculation over a replaced wide glyph --- #


def test_keycap_completing_over_a_replaced_wide_glyph_does_not_resurrect_it():
    """The retraction restores the run's own cells, not the glyph they replaced.

    'A1' overwrites a wide glyph: 'A' lands on its head and '1' on its
    continuation column. When the keycap tail arrives in the next chunk the '1'
    is retracted and repainted two cells wide — and the ❌ it displaced must not
    come back with it.
    """
    board = clustered_board(width=8, height=1)
    board.parser.feed("❌")  # wide: head at col 0, continuation at col 1
    board.parser.feed("\x1b[1;1H")
    board.parser.feed("A1")

    board.parser.feed("️⃣")  # variation selector + enclosing keycap

    row = cells(board)
    assert row[0] == "A"
    assert row[1] == "1️⃣"
    assert isinstance(board.blitter.current_page.grid[0][1][1], WideHead)
    assert row[2] == ""  # its continuation, not a resurrected ❌
    assert board.cursor.x == 3


# --- mixed runs --- #


def test_ascii_is_flushed_before_a_non_ascii_cluster_in_the_same_run():
    """One write holding ASCII, a wide cluster, then more ASCII."""
    board = clustered_board(width=12, height=1)

    board.parser.feed("abc\U0001f600def")

    assert [cell for cell in cells(board)[:8]] == ["a", "b", "c", "\U0001f600", "", "d", "e", "f"]
    assert board.capture_text() == "abc\U0001f600def"
    assert board.cursor.x == 8


def test_cluster_wider_than_the_terminal_is_skipped():
    """A width-2 cluster cannot be shown on a one-column screen.

    The clustered writer has its own copy of this rule; the plain writer's is
    covered in test_wide_characters.
    """
    board = clustered_board(width=1, height=1)

    board.parser.feed("a❌b")

    assert board.capture_text() == "b"
    assert board.cursor.x == 1


def test_empty_write_under_clustering_is_a_no_op():
    board = clustered_board(width=5, height=1)
    board.parser.feed("A")

    board.blitter.write_text("")

    assert cells(board)[0] == "A"
    assert board.cursor.x == 1


# --- retraction at the right margin --- #


def test_retraction_that_reaches_the_right_margin_arms_a_pending_wrap():
    """Widening a cluster can land it exactly on the margin.

    'AB1' puts the candidate at the last column but one; the keycap tail widens
    it to two cells, filling the row. The cursor must end armed for wrap rather
    than already on the next line.
    """
    board = clustered_board(width=4, height=2)
    board.parser.feed("AB1")

    board.parser.feed("️⃣")

    assert board.capture_text() == "AB1️⃣"
    assert (board.cursor.x, board.cursor.y) == (4, 0)  # armed, not yet wrapped


def test_retraction_at_the_margin_without_autowrap_clamps_instead():
    """Same widening with DECAWM off parks the cursor inside the row."""
    board = clustered_board(width=4, height=2)
    board.parser.feed("\x1b[?7l")
    board.parser.feed("AB1")

    board.parser.feed("️⃣")

    assert board.capture_text() == "AB1️⃣"
    assert (board.cursor.x, board.cursor.y) == (3, 0)


def test_a_pending_prefix_invalidated_by_a_cursor_move_is_discarded():
    """A forward-joining prefix is held across chunks, but only where it was left.

    U+0600 joins whatever follows, so it is parked rather than painted. If the
    cursor moves before the next chunk arrives, the join can no longer happen
    and the prefix must be dropped instead of teleporting to the new position.
    """
    board = clustered_board(width=10, height=3)
    board.parser.feed("؀")  # parked, not painted

    board.parser.feed("\x1b[2;5H")  # move away — the prefix is now stale
    board.parser.feed("A")

    assert board.blitter.current_page.get_line_text(0) == " " * 10
    assert board.blitter.current_page.get_line_text(1) == "    A     "
    assert (board.cursor.x, board.cursor.y) == (5, 1)


def test_speculation_is_abandoned_when_its_cell_changed_underneath():
    """The candidate cell is re-read before retracting, not trusted.

    DECFRA can overwrite the cell without touching the cursor, so every other
    validity check still passes. The stored text no longer matches what is on
    screen, and the combining mark is dropped rather than corrupting the fill.
    """
    board = clustered_board(width=8, height=1)
    board.parser.feed("e")
    board.parser.feed("\x1b[88;1;1;1;1$x")  # fill (0,0) with 'X', cursor unmoved

    board.parser.feed("́")

    assert board.blitter.current_page.get_line_text(0) == "X       "
    assert board.cursor.x == 1


def test_widening_over_a_neighbouring_wide_glyph_leaves_no_orphan():
    """The snapshot covers the displaced glyph's continuation column too.

    The keycap candidate sits at column 0 with a wide glyph at columns 1-2. When
    it widens it consumes that glyph's head, so the snapshot has to reach one
    column further or the continuation is left stranded.
    """
    board = clustered_board(width=8, height=1)
    board.parser.feed("\x1b[1;2H❌")
    board.parser.feed("\x1b[1;1H")
    board.parser.feed("1")

    board.parser.feed("️⃣")

    row = cells(board)
    assert row[0] == "1️⃣"
    assert isinstance(board.blitter.current_page.grid[0][0][1], WideHead)
    assert row[1] == ""  # its own continuation
    assert row[2] == " "  # the displaced glyph's continuation was cleared
    assert board.cursor.x == 2
