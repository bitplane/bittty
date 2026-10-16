"""Images drawn in text: the rasterizer, and rows of text with images drawn over them."""

from bittty.image import Band, Image, Placement
from bittty.style import Color, Style
from bittty.terminals import StdioTerminal
from bittty.terminals.raster import HALF_BLOCKS, SPACES, composite, rasterize
from bittty.video import CONTINUATION, WideHead

RED, BLUE, CLEAR = (255, 0, 0, 255), (0, 0, 255, 255), (0, 0, 0, 0)
PLAIN = Style()


def _image(*rows):
    """An image from rows of RGBA pixels."""
    return Image(len(rows[0]), len(rows), b"".join(bytes(pixel) for row in rows for pixel in row))


def _rgb(pixel):
    return Color("rgb", pixel[:3])


def test_half_blocks_draw_the_top_pixel_in_front_of_the_bottom():
    placement = Placement(_image([RED], [BLUE]), 0, (1, 2))
    assert rasterize(placement, HALF_BLOCKS) == (((_rgb(RED), _rgb(BLUE), "▀"),),)


def test_a_cell_of_one_colour_is_a_space_on_it():
    placement = Placement(_image([RED], [RED]), 0, (1, 2))
    assert rasterize(placement, HALF_BLOCKS) == (((None, _rgb(RED), " "),),)


def test_a_pixel_takes_the_mean_of_the_image_pixels_it_covers():
    placement = Placement(_image([RED, BLUE]), 0, (2, 1))
    assert rasterize(placement, SPACES) == (((None, Color("rgb", (127, 0, 127)), " "),),)


def test_a_pixel_mostly_clear_is_transparent_and_shows_what_is_behind():
    placement = Placement(_image([RED], [CLEAR]), 0, (1, 2))
    assert rasterize(placement, HALF_BLOCKS) == (((_rgb(RED), None, "▀"),),)


def test_a_cell_wholly_clear_is_left_alone():
    placement = Placement(_image([CLEAR, RED], [CLEAR, RED]), 0, (1, 2))
    assert rasterize(placement, HALF_BLOCKS) == ((None, (None, _rgb(RED), " ")),)


def test_cells_the_image_only_partly_reaches_are_clear_beyond_it():
    placement = Placement(_image([RED], [RED], [BLUE]), 0, (1, 2))
    assert rasterize(placement, HALF_BLOCKS) == (((None, _rgb(RED), " "),), ((_rgb(BLUE), None, "▀"),))


def test_images_are_drawn_over_text_in_order():
    under = Placement(_image([RED, RED], [RED, RED]), 0, (1, 2))
    over = Placement(_image([BLUE], [BLUE]), 1, (1, 2))
    row = composite([(PLAIN, "a"), (PLAIN, "b"), (PLAIN, "c")], (Band(under, 0), Band(over, 0)), HALF_BLOCKS)
    assert row == [(Style(bg=_rgb(RED)), " "), (Style(bg=_rgb(BLUE)), " "), (PLAIN, "c")]


def test_clear_pixels_show_the_background_of_the_text_behind():
    behind = Style(bg=Color("indexed", 2), bold=True)
    placement = Placement(_image([RED], [CLEAR]), 0, (1, 2))
    row = composite([(behind, "a")], (Band(placement, 0),), HALF_BLOCKS)
    assert row == [(Style(fg=_rgb(RED), bg=Color("indexed", 2)), "▀")]


def test_an_image_over_half_a_wide_glyph_blanks_the_other_half():
    placement = Placement(_image([RED], [RED]), 1, (1, 2))
    wide = Style(bold=True)
    row = [(wide, WideHead("中")), (wide, CONTINUATION), (wide, WideHead("中")), (wide, CONTINUATION)]
    assert composite(row, (Band(placement, 0),), HALF_BLOCKS)[:2] == [(wide, " "), (Style(bg=_rgb(RED)), " ")]
    placement = Placement(_image([RED], [RED]), 2, (1, 2))
    assert composite(row, (Band(placement, 0),), HALF_BLOCKS)[2:] == [(Style(bg=_rgb(RED)), " "), (wide, " ")]


def test_an_image_is_cut_at_the_edge_of_the_row():
    placement = Placement(_image([RED, RED, RED], [RED, RED, RED]), 1, (1, 2))
    assert len(composite([(PLAIN, "a"), (PLAIN, "b")], (Band(placement, 0),), HALF_BLOCKS)) == 2


def test_the_terminal_paints_images_over_the_rows_they_are_on(capsys):
    display = StdioTerminal()
    display.render_screen()
    display.board.blitter.current_page.place(1, Placement(_image([RED], [BLUE]), 2, (1, 2)))
    capsys.readouterr()
    display.render_screen()
    assert "\033[2H  \033[38;2;255;0;0;48;2;0;0;255m▀\033[0m" in capsys.readouterr().out
