from bittty import Board
from bittty import constants
from bittty.parser import Parser
from bittty.style import Style, parse_sgr_sequence


def test_write_cell_overwrite():
    board = Board(width=10, height=1)
    parser = Parser(board)
    parser = Parser(board)
    parser.feed("\x1b[31m")  # Set red color
    parser.feed("A")
    assert board.blitter.current_page.get_line_text(0) == "A         "
    assert board.blitter.current_page.get_cell(0, 0) == (parse_sgr_sequence("\x1b[31m"), "A")
    assert board.cursor.x == 1

    parser.feed("\x1b[32m")  # Set green color
    parser.feed("B")
    assert board.blitter.current_page.get_line_text(0) == "AB        "
    assert board.blitter.current_page.get_cell(1, 0) == (parse_sgr_sequence("\x1b[32m"), "B")
    assert board.cursor.x == 2

    board.cursor.set_position(0, 0)
    parser.feed("\x1b[34m")  # Set blue color
    parser.feed("C")
    assert board.blitter.current_page.get_line_text(0) == "CB        "
    assert board.blitter.current_page.get_cell(0, 0) == (parse_sgr_sequence("\x1b[34m"), "C")
    assert board.cursor.x == 1


def test_write_cell_insert_mode():
    board = Board(width=10, height=1)
    parser = Parser(board)
    parser = Parser(board)
    parser.feed("\x1b[31m")  # Set red color
    parser.feed("A")
    parser.feed("\x1b[32m")  # Set green color
    parser.feed("B")
    board.cursor.set_position(0, 0)
    board.modes.insert_mode = True
    parser.feed("\x1b[34m")  # Set blue color
    parser.feed("C")
    assert board.blitter.current_page.get_line_text(0) == "CAB       "
    assert board.blitter.current_page.get_cell(0, 0) == (parse_sgr_sequence("\x1b[34m"), "C")
    assert board.blitter.current_page.get_cell(1, 0) == (parse_sgr_sequence("\x1b[31m"), "A")
    assert board.blitter.current_page.get_cell(2, 0) == (parse_sgr_sequence("\x1b[32m"), "B")
    assert board.cursor.x == 1


def test_write_cell_autowrap():
    board = Board(width=3, height=2)
    parser = Parser(board)
    parser.feed("\x1b[31m")  # Set red color
    parser.feed("A")
    parser.feed("\x1b[32m")  # Set green color
    parser.feed("B")
    parser.feed("\x1b[34m")  # Set blue color
    parser.feed("C")
    assert board.blitter.current_page.get_line_text(0) == "ABC"
    assert board.cursor.x == 3
    assert board.cursor.y == 0

    parser.feed("\x1b[33m")  # Set yellow color
    parser.feed("D")  # Should wrap
    assert board.blitter.current_page.get_line_text(1) == "D  "
    assert board.cursor.x == 1
    assert board.cursor.y == 1


def test_clear_rect():
    board = Board(width=5, height=5)
    for y in range(5):
        for x in range(5):
            board.blitter.current_page.set_cell(x, y, "X", "\x1b[31m")

    board.blitter.clear_rect(1, 1, 3, 3)

    for y in range(5):
        for x in range(5):
            if 1 <= x <= 3 and 1 <= y <= 3:
                assert board.blitter.current_page.get_cell(x, y) == (Style(), " ")
            else:
                assert board.blitter.current_page.get_cell(x, y) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_clear_screen():
    board = Board(width=10, height=5)
    for y in range(5):
        for x in range(10):
            board.blitter.current_page.set_cell(x, y, chr(ord("A") + y))

    board.cursor.set_position(5, 2)

    # Mode 0: Clear from cursor to end of terminal
    board.blitter.clear_screen(constants.ERASE_FROM_CURSOR_TO_END)
    assert board.blitter.current_page.get_line_text(0) == "AAAAAAAAAA"
    assert board.blitter.current_page.get_line_text(1) == "BBBBBBBBBB"
    assert board.blitter.current_page.get_line_text(2) == "CCCCC     "
    assert board.blitter.current_page.get_line_text(3) == "          "
    assert board.blitter.current_page.get_line_text(4) == "          "

    # Reset terminal
    for y in range(5):
        for x in range(10):
            board.blitter.current_page.set_cell(x, y, chr(ord("A") + y))
    board.cursor.set_position(5, 2)

    # Mode 1: Clear from beginning of terminal to cursor
    board.blitter.clear_screen(constants.ERASE_FROM_START_TO_CURSOR)
    assert board.blitter.current_page.get_line_text(0) == "          "
    assert board.blitter.current_page.get_line_text(1) == "          "
    assert board.blitter.current_page.get_line_text(2) == "      CCCC"
    assert board.blitter.current_page.get_line_text(3) == "DDDDDDDDDD"
    assert board.blitter.current_page.get_line_text(4) == "EEEEEEEEEE"

    # Reset terminal
    for y in range(5):
        for x in range(10):
            board.blitter.current_page.set_cell(x, y, chr(ord("A") + y))
    board.cursor.set_position(5, 2)

    # Mode 2: Clear entire terminal
    board.blitter.clear_screen(constants.ERASE_ALL)
    for y in range(5):
        assert board.blitter.current_page.get_line_text(y) == "          "


def test_clear_line():
    board = Board(width=10, height=1)
    for x in range(10):
        board.blitter.current_page.set_cell(x, 0, "X")
    board.cursor.set_position(5, 0)

    # Mode 0: Clear from cursor to end of line
    board.blitter.clear_line(constants.ERASE_FROM_CURSOR_TO_END)
    assert board.blitter.current_page.get_line_text(0) == "XXXXX     "

    # Reset
    for x in range(10):
        board.blitter.current_page.set_cell(x, 0, "X")
    board.cursor.set_position(5, 0)

    # Mode 1: Clear from beginning of line to cursor
    board.blitter.clear_line(constants.ERASE_FROM_START_TO_CURSOR)
    assert board.blitter.current_page.get_line_text(0) == "      XXXX"

    # Reset
    for x in range(10):
        board.blitter.current_page.set_cell(x, 0, "X")
    board.cursor.set_position(5, 0)

    # Mode 2: Clear entire line
    board.blitter.clear_line(constants.ERASE_ALL)
    assert board.blitter.current_page.get_line_text(0) == "          "


def test_insert_lines():
    board = Board(width=10, height=5)
    for y in range(5):
        board.blitter.current_page.set(0, y, f"Line {y}")
    board.cursor.set_position(0, 2)

    board.blitter.insert_lines(1)
    assert board.blitter.current_page.get_line_text(0) == "Line 0    "
    assert board.blitter.current_page.get_line_text(1) == "Line 1    "
    assert board.blitter.current_page.get_line_text(2) == "          "
    assert board.blitter.current_page.get_line_text(3) == "Line 2    "
    assert board.blitter.current_page.get_line_text(4) == "Line 3    "

    # Insert multiple lines
    board = Board(width=10, height=5)
    for y in range(5):
        board.blitter.current_page.set(0, y, f"Line {y}")
    board.cursor.set_position(0, 1)
    board.blitter.insert_lines(2)
    assert board.blitter.current_page.get_line_text(0) == "Line 0    "
    assert board.blitter.current_page.get_line_text(1) == "          "
    assert board.blitter.current_page.get_line_text(2) == "          "
    assert board.blitter.current_page.get_line_text(3) == "Line 1    "
    assert board.blitter.current_page.get_line_text(4) == "Line 2    "


def test_delete_lines():
    board = Board(width=10, height=5)
    for y in range(5):
        board.blitter.current_page.set(0, y, f"Line {y}")
    board.cursor.set_position(0, 1)

    board.blitter.delete_lines(1)
    assert board.blitter.current_page.get_line_text(0) == "Line 0    "
    assert board.blitter.current_page.get_line_text(1) == "Line 2    "
    assert board.blitter.current_page.get_line_text(2) == "Line 3    "
    assert board.blitter.current_page.get_line_text(3) == "Line 4    "
    assert board.blitter.current_page.get_line_text(4) == "          "

    # Delete multiple lines
    board = Board(width=10, height=5)
    for y in range(5):
        board.blitter.current_page.set(0, y, f"Line {y}")
    board.cursor.set_position(0, 0)
    board.blitter.delete_lines(2)
    assert board.blitter.current_page.get_line_text(0) == "Line 2    "
    assert board.blitter.current_page.get_line_text(1) == "Line 3    "
    assert board.blitter.current_page.get_line_text(2) == "Line 4    "
    assert board.blitter.current_page.get_line_text(3) == "          "
    assert board.blitter.current_page.get_line_text(4) == "          "


def test_insert_characters():
    board = Board(width=10, height=1)
    board.blitter.current_page.set(0, 0, "ABCDEFGHIJ")
    board.cursor.set_position(2, 0)

    board.blitter.insert_characters(3)
    assert board.blitter.current_page.get_line_text(0) == "AB   CDEFG"


def test_delete_characters():
    board = Board(width=10, height=5)
    board.blitter.current_page.set(0, 0, "12345")
    board.cursor.x = 2
    board.cursor.y = 0
    board.blitter.delete_characters(2)
    assert board.blitter.current_page.get_line_text(0) == "125       "


def test_delete_characters_from_middle_of_line():
    board = Board(width=10, height=5)
    board.blitter.current_page.set(0, 0, "123456789")
    board.cursor.x = 2
    board.cursor.y = 0
    board.blitter.delete_characters(3)
    assert board.blitter.current_page.get_line_text(0) == "126789    "


def test_delete_characters_at_end_of_line_no_effect():
    board = Board(width=10, height=5)
    board.blitter.current_page.set(0, 0, "abc")
    board.cursor.x = 3
    board.cursor.y = 0
    board.blitter.delete_characters(1)
    assert board.blitter.current_page.get_line_text(0) == "abc       "


def test_delete_characters_beyond_end_of_line():
    board = Board(width=10, height=5)
    board.blitter.current_page.set(0, 0, "12345")
    board.cursor.x = 2
    board.cursor.y = 0
    board.blitter.delete_characters(10)  # Attempt to delete more than available
    assert board.blitter.current_page.get_line_text(0) == "12        "


def test_delete_characters_from_empty_line():
    board = Board(width=10, height=5)
    board.cursor.x = 0
    board.cursor.y = 0
    board.blitter.delete_characters(5)
    assert board.blitter.current_page.get_line_text(0) == "          "


def test_delete_last_character_on_line():
    board = Board(width=10, height=5)
    board.blitter.current_page.set(0, 0, "abcde")
    board.cursor.x = 4
    board.cursor.y = 0
    board.blitter.delete_characters(1)
    assert board.blitter.current_page.get_line_text(0) == "abcd      "


def test_insert_characters_at_end_of_line():
    board = Board(width=10, height=5)
    board.blitter.current_page.set(0, 0, "12345")
    board.cursor.x = 5
    board.cursor.y = 0
    board.blitter.insert_characters(2)
    assert board.blitter.current_page.get_line_text(0) == "12345     "


def test_insert_characters_invalid_cursor():
    board = Board(width=10, height=5)
    board.cursor.y = 10  # Invalid cursor position
    board.blitter.insert_characters(1)
    # Should not raise an error and do nothing


def test_insert_characters_with_padding_preserves_style_objects():
    """Test that insert beyond row length creates proper Style objects when padding."""
    board = Board(width=10, height=5)
    board.cursor.x = 8  # Near end of line
    board.cursor.y = 0

    # Insert text that triggers padding in page.insert
    board.blitter.insert_characters(2, Style(italic=True))

    # Check that all cells have proper Style objects
    row = board.blitter.current_page.grid[0]
    for style, char in row:
        assert isinstance(style, Style), f"Expected Style object, got {type(style)}"


def test_delete_characters_invalid_cursor():
    board = Board(width=10, height=5)
    board.cursor.y = 10  # Invalid cursor position
    board.blitter.delete_characters(1)
    # Should not raise an error and do nothing


def test_delete_characters_preserves_style_objects():
    """Test that delete_characters creates proper Style objects, not empty strings."""
    board = Board(width=10, height=5)
    board.blitter.current_page.set(0, 0, "hello", Style(bold=True))
    board.cursor.x = 1
    board.cursor.y = 0

    # This was the source of the bug - delete_characters -> page.delete
    board.blitter.delete_characters(3)

    # Check that padding cells have proper Style objects, not empty strings
    row = board.blitter.current_page.grid[0]
    for style, char in row:
        assert isinstance(style, Style), f"Expected Style object, got {type(style)}"
        assert hasattr(style, "bold"), "Style object should have bold attribute"
