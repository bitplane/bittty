"""Images on the page: placements whose bands ride the rows they cover."""

from bittty import Board, MemoryConnection
from bittty.image import Band, Image, Placement
from bittty.terminals import Terminal
from bittty.terminals.scrollback import MemoryScrollback, ScrollbackLine
from bittty.video import Video


def _placement(rows=2, column=0, cell=(10, 20)):
    """An opaque red image `rows` cells high and two wide, at `cell`-sized cells."""
    width, height = 2 * cell[0], rows * cell[1]
    return Placement(Image(width, height, b"\xff\x00\x00\xff" * width * height), column, cell)


def _bands(page):
    return [tuple((band.placement, band.row) for band in bands) for bands in page.bands]


def test_an_image_covers_the_cells_its_pixels_reach():
    image = Image(25, 41, bytes(25 * 41 * 4))
    placement = Placement(image, 3, (10, 20))
    assert (placement.columns, placement.rows) == (3, 3)


def test_placing_an_image_bands_each_row_it_covers():
    page = Video(5, 4)
    placement = _placement(rows=2)
    page.place(1, placement)
    assert _bands(page) == [(), ((placement, 0),), ((placement, 1),), ()]


def test_an_image_placed_near_the_bottom_is_cut_at_the_page():
    page = Video(5, 3)
    placement = _placement(rows=3)
    page.place(1, placement)
    assert _bands(page) == [(), ((placement, 0),), ((placement, 1),)]


def test_images_placed_over_each_other_stack_in_order():
    page = Video(5, 2)
    under, over = _placement(rows=1), _placement(rows=1, column=1)
    page.place(0, under)
    page.place(0, over)
    assert _bands(page)[0] == ((under, 0), (over, 0))


def test_placing_an_image_damages_its_rows():
    page = Video(5, 4)
    seen = page.observe()
    page.place(1, _placement(rows=2))
    assert page.changed_rows(seen) == [1, 2]


def test_bands_scroll_up_with_their_rows():
    page = Video(5, 3)
    placement = _placement(rows=2)
    page.place(1, placement)
    page.scroll_region_up(0, 2, 1)
    assert _bands(page) == [((placement, 0),), ((placement, 1),), ()]


def test_bands_scroll_down_with_their_rows():
    page = Video(5, 3)
    placement = _placement(rows=2)
    page.place(0, placement)
    page.scroll_region_down(0, 2, 1)
    assert _bands(page) == [(), ((placement, 0),), ((placement, 1),)]


def test_bands_scroll_within_a_region():
    page = Video(5, 4)
    placement = _placement(rows=1)
    page.place(2, placement)
    page.scroll_region_up(1, 2, 1)
    assert _bands(page) == [(), ((placement, 0),), (), ()]


def test_bands_scroll_with_a_coloured_full_width_rectangle():
    page = Video(5, 3)
    placement = _placement(rows=1)
    page.place(1, placement)
    page.scroll_rectangle_up(0, 2, 1, style_or_ansi="\x1b[41m")
    page.scroll_rectangle_down(0, 2, 2, style_or_ansi="\x1b[41m")
    assert _bands(page) == [(), (), ((placement, 0),)]


def test_a_part_width_rectangle_leaves_bands_on_their_rows():
    # As with DECDWL, a row-wide band cannot move without the cells beside the rectangle.
    page = Video(5, 3)
    placement = _placement(rows=1)
    page.place(1, placement)
    page.scroll_rectangle_up(0, 2, 1, left=1, right=3)
    assert _bands(page) == [(), ((placement, 0),), ()]


def test_the_whole_page_scrolls_bands():
    page = Video(5, 3)
    placement = _placement(rows=1)
    page.place(1, placement)
    page.scroll_up(1)
    assert _bands(page) == [((placement, 0),), (), ()]
    page.scroll_down(2)
    assert _bands(page) == [(), (), ((placement, 0),)]


def test_a_detached_line_carries_its_bands():
    page = Video(5, 3)
    placement = _placement(rows=1)
    page.place(0, placement)
    assert page.line(0).bands == (Band(placement, 0),)


def test_resizing_shorter_drops_the_bands_cut_off():
    page = Video(5, 3)
    placement = _placement(rows=3)
    page.place(0, placement)
    page.resize(4, 2)
    assert _bands(page) == [((placement, 0),), ((placement, 1),)]
    page.resize(4, 3)
    assert _bands(page)[2] == ()


def test_reflow_holds_an_image_row_while_other_lines_rewrap():
    page = Video(4, 3)
    page.set(0, 0, "abcd")
    page.set_line_wrapped(0)
    page.set(0, 1, "ef")
    placement = _placement(rows=1)
    page.place(2, placement)
    page.set(0, 2, "ghij")
    page.reflow(6, 3, (0, 0))
    assert [page.get_line_text(y) for y in range(3)] == ["abcdef", "ghij  ", "      "]
    assert _bands(page) == [(), ((placement, 0),), ()]


def test_reflow_keeps_a_blank_image_row_below_the_cursor():
    page = Video(4, 3)
    page.set(0, 0, "a")
    placement = _placement(rows=1)
    page.place(2, placement)
    _, cut = page.reflow(4, 2, (0, 1))
    assert [line.cells[0][1] for line in cut] == ["a"]
    assert _bands(page) == [(), ((placement, 0),)]


def test_reflow_cuts_a_held_row_at_the_new_width():
    page = Video(4, 1)
    page.set(0, 0, "abcd")
    page.place(0, _placement(rows=1))
    position, _ = page.reflow(2, 1, (3, 0))
    assert page.get_line_text(0) == "ab"
    assert position == (1, 0)


def test_a_hard_reset_clears_every_image():
    board = Board(width=5, height=3)
    board.host.attach(MemoryConnection())
    for page in board.blitter.videos:
        page.place(0, _placement(rows=1))
    board.feed_host_data(b"\x1bc")
    assert all(_bands(page) == [(), (), ()] for page in board.blitter.videos)


def test_a_scrollback_line_keeps_its_bands_at_the_cell_its_row_starts():
    first, second = Band(_placement(rows=1), 0), Band(_placement(rows=1), 0)
    style = Video(1, 1).get_cell(0, 0)[0]
    line = ScrollbackLine.join(
        [ScrollbackLine.of([(style, "a")] * 3, bands=(first,)), ScrollbackLine.of([(style, "b")], bands=(second,))]
    )
    assert line.bands == ((0, first), (3, second))


def test_rows_scrolled_into_history_keep_their_images():
    board = Board(width=5, height=2)
    board.host.attach(MemoryConnection())
    terminal = Terminal(board, MemoryScrollback())
    terminal.attach()
    placement = _placement(rows=1)
    board.blitter.current_page.place(0, placement)
    board.feed_host_data(b"\r\n\r\n")
    assert terminal.scrollback.line(0).bands == ((0, Band(placement, 0)),)
