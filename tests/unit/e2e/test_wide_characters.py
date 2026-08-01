"""Width-2 character behaviour across the terminal cell grid."""

import pytest

from bittty import Board, TerminalCaps, Video, WidthPolicy
from bittty.style import Style
from bittty.video import WideHead


def row_chars(board: Board, y: int = 0) -> list[str]:
    return [char for _, char in board.blitter.current_buffer.grid[y]]


def assert_valid_rows(board: Board) -> None:
    for row in board.blitter.current_buffer.grid:
        for x, (_, char) in enumerate(row):
            if char == "":
                assert x > 0
                assert isinstance(row[x - 1][1], WideHead)
                assert row[x - 1][0] == row[x][0]
            elif isinstance(char, WideHead):
                assert x + 1 < len(row)
                assert row[x + 1][1] == ""


def test_width_policy_defaults_ambiguous_to_narrow():
    assert WidthPolicy().width("A") == 1
    assert WidthPolicy().width("❌") == 2
    assert WidthPolicy().width("你") == 2
    assert WidthPolicy().width("·") == 1
    assert WidthPolicy(ambiguous_width=2).width("·") == 2


def test_width_policy_rejects_invalid_ambiguous_width():
    with pytest.raises(ValueError):
        WidthPolicy(ambiguous_width=3)


def test_width_policy_measures_complete_graphemes():
    policy = WidthPolicy()
    assert policy.grapheme_width("\u0301") == 0
    assert policy.grapheme_width("e\u0301") == 1
    assert policy.grapheme_width("🧑\u200d🌾") == 2


def test_board_uses_its_configured_ambiguous_width():
    board = Board(width=4, height=1, width_policy=WidthPolicy(ambiguous_width=2))
    board.parser.feed("·")

    assert row_chars(board) == ["·", "", " ", " "]
    assert board.cursor.x == 2


def test_stored_width_survives_policy_changes():
    board = Board(width=8, height=1, width_policy=WidthPolicy(ambiguous_width=2))
    board.parser.feed("·")
    board.set_ambiguous_width(1)
    board.blitter.current_buffer.normalize_row(0)
    board.parser.feed("·")

    assert row_chars(board)[:3] == ["·", "", "·"]
    assert isinstance(row_chars(board)[0], WideHead)
    assert not isinstance(row_chars(board)[2], WideHead)
    assert_valid_rows(board)

    board.cursor.x = 0
    board.blitter.insert_characters(1)
    assert row_chars(board)[:4] == [" ", "·", "", "·"]
    assert_valid_rows(board)


def test_detected_width_sets_automatic_baseline_but_not_explicit_baseline():
    automatic = Board(width=4, height=1)
    automatic.set_caps(TerminalCaps(ambiguous_width=2))
    automatic.parser.feed("·")
    assert row_chars(automatic)[:2] == ["·", ""]

    explicit = Board(width=4, height=1, width_policy=WidthPolicy(ambiguous_width=1))
    explicit.set_caps(TerminalCaps(ambiguous_width=2))
    explicit.parser.feed("·")
    assert row_chars(explicit)[:2] == ["·", " "]


def test_mode_8840_changes_future_writes_and_ris_restores_baseline():
    board = Board(width=8, height=1, width_policy=WidthPolicy(ambiguous_width=2))
    board.parser.feed("\x1b[?8840l·")
    assert board.width_policy.ambiguous_width == 1
    assert row_chars(board)[0] == "·"

    board.parser.feed("\x1b[!p")  # DECSTR preserves the runtime width mode
    assert board.width_policy.ambiguous_width == 1

    board.parser.feed("\x1bc")  # RIS restores the constructor baseline
    assert board.width_policy.ambiguous_width == 2
    board.parser.feed("·")
    assert row_chars(board)[:2] == ["·", ""]


def test_caps_update_during_mode_override_only_changes_the_next_reset_baseline():
    board = Board(width=4, height=1)
    board.parser.feed("\x1b[?8840h")
    board.set_caps(TerminalCaps(ambiguous_width=1))

    assert board.width_policy.ambiguous_width == 2
    board.parser.feed("\x1bc")
    assert board.width_policy.ambiguous_width == 1


def test_wide_character_uses_head_and_continuation_cells():
    board = Board(width=6, height=2)
    board.parser.feed("A❌B")

    assert row_chars(board) == ["A", "❌", "", "B", " ", " "]
    assert board.cursor.x == 4
    assert board.capture_text() == "A❌B"
    assert board.capture_pane().count("❌") == 1
    assert_valid_rows(board)


def test_wide_character_wraps_before_lone_final_column():
    board = Board(width=5, height=2)
    board.cursor.x = 4
    board.parser.feed("❌")

    assert row_chars(board, 0) == [" "] * 5
    assert row_chars(board, 1)[:2] == ["❌", ""]
    assert (board.cursor.x, board.cursor.y) == (2, 1)


def test_wide_character_exact_fit_keeps_delayed_wrap():
    board = Board(width=5, height=2)
    board.cursor.x = 3
    board.parser.feed("❌")

    assert row_chars(board, 0)[3:] == ["❌", ""]
    assert (board.cursor.x, board.cursor.y) == (5, 0)
    board.parser.feed("X")
    assert row_chars(board, 1)[0] == "X"


def test_wide_character_without_autowrap_backs_up_to_fit():
    board = Board(width=5, height=2)
    board.modes.auto_wrap = False
    board.cursor.x = 4
    board.parser.feed("❌")

    assert row_chars(board, 0)[3:] == ["❌", ""]
    assert (board.cursor.x, board.cursor.y) == (4, 0)


@pytest.mark.parametrize("x", [1, 2])
def test_overwriting_either_half_erases_the_whole_wide_glyph(x):
    board = Board(width=6, height=1)
    board.parser.feed("A❌BC")
    board.cursor.x = x
    board.parser.feed("X")

    assert row_chars(board) == ["A", " " if x == 2 else "X", "X" if x == 2 else " ", "B", "C", " "]
    assert_valid_rows(board)


def test_insert_and_delete_repair_split_wide_glyphs():
    board = Board(width=8, height=1)
    board.parser.feed("A❌BCD")

    board.cursor.x = 2  # continuation half
    board.blitter.insert_characters(1)
    assert row_chars(board) == ["A", " ", " ", " ", "B", "C", "D", " "]
    assert_valid_rows(board)

    board = Board(width=8, height=1)
    board.parser.feed("A❌BCD")
    board.cursor.x = 1
    board.blitter.delete_characters(1)
    assert row_chars(board) == ["A", " ", "B", "C", "D", " ", " ", " "]
    assert_valid_rows(board)


def test_erase_and_clear_rectangle_expand_over_wide_glyph():
    board = Board(width=7, height=2)
    board.parser.feed("A❌BCD")
    board.cursor.x = 2
    board.blitter.erase_characters(1)
    assert row_chars(board, 0)[:4] == ["A", " ", " ", "B"]

    board.cursor.set_position(0, 1)
    board.parser.feed("A❌BCD")
    board.blitter.clear_rect(2, 1, 2, 1)
    assert row_chars(board, 1)[:4] == ["A", " ", " ", "B"]
    assert_valid_rows(board)


def test_resize_drops_wide_glyph_split_by_new_edge():
    video = Video(width=5, height=1)
    video.set(3, 0, "❌")
    video.resize(4, 1)

    assert [char for _, char in video.grid[0]] == [" ", " ", " ", " "]


def test_attribute_change_applies_once_to_both_cells():
    board = Board(width=5, height=1)
    board.parser.feed("❌")
    board.parser.feed("\x1b[1;1;1;2;1$t")  # DECRARA: toggle bold over both cells

    head, continuation = board.blitter.current_buffer.grid[0][:2]
    assert head[0].bold is True
    assert continuation == (head[0], "")


def test_hyperlink_lookup_from_continuation_uses_same_extent():
    board = Board(width=5, height=1)
    board.parser.feed("\x1b]8;id=wide;https://example.com\x07❌\x1b]8;;\x07")

    assert board.link_at(0, 0) == ("https://example.com", "wide")
    assert board.link_at(1, 0) == ("https://example.com", "wide")
    assert board.blitter.current_buffer.link_extent(1, 0) == ("https://example.com", "wide", 0, 1)


def test_copy_rectangle_does_not_copy_half_a_wide_glyph():
    board = Board(width=8, height=2)
    board.parser.feed("A❌BCD")
    board.blitter.copy_rectangle([1, 3, 1, 3, 1, 2, 1, 1])

    assert board.blitter.current_buffer.get_cell(0, 1) == (Style(), " ")
    assert_valid_rows(board)


def test_character_wider_than_the_terminal_is_skipped():
    """A width-2 glyph cannot be represented on a one-column screen."""
    board = Board(width=1, height=1)

    board.parser.feed("a❌b")

    assert board.capture_text() == "b"
    assert board.cursor.x == 1


def test_insert_mode_shifts_content_for_a_wide_character():
    """IRM with a width-2 glyph, outside grapheme clustering."""
    board = Board(width=10, height=1)
    board.parser.feed("ABCDEF")
    board.parser.feed("\x1b[1;1H\x1b[4h")

    board.parser.feed("❌")

    assert board.capture_text() == "❌ABCDEF"
    assert board.cursor.x == 2
