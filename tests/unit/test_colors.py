"""Colour reduction: styles brought within the colours a venue can show."""

from bittty import TerminalCaps
from bittty.style import Color, Style
from bittty.terminals import StdioTerminal
from bittty.terminals.colors import reduce_style
from bittty.terminals.scrollback import MemoryScrollback


def _rgb(*rgb):
    return Color("rgb", rgb)


def _indexed(index):
    return Color("indexed", index)


def test_256_colours_take_the_nearest_of_the_cube_and_greys():
    assert reduce_style(Style(fg=_rgb(255, 0, 0)), "256") == Style(fg=_indexed(196))
    assert reduce_style(Style(bg=_rgb(95, 135, 175)), "256") == Style(bg=_indexed(67))
    assert reduce_style(Style(fg=_rgb(128, 128, 128)), "256") == Style(fg=_indexed(244))


def test_256_colours_keep_indexed_colours_and_map_underline_colour():
    style = Style(fg=_indexed(200), underline=True, underline_color=_rgb(0, 0, 255))
    assert reduce_style(style, "256") == Style(fg=_indexed(200), underline=True, underline_color=_indexed(21))


def test_16_colours_take_the_nearest_ansi_colour():
    assert reduce_style(Style(fg=_rgb(250, 10, 10)), "16") == Style(fg=_indexed(9))
    assert reduce_style(Style(bg=_indexed(196)), "16") == Style(bg=_indexed(9))
    assert reduce_style(Style(fg=_indexed(3), bg=Color("default")), "16") == Style(fg=_indexed(3), bg=Color("default"))


def test_16_colours_have_no_underline_colour():
    assert reduce_style(Style(underline=True, underline_color=_indexed(1)), "16") == Style(underline=True)


def test_monochrome_keeps_the_attributes_and_drops_the_colours():
    style = Style(fg=_rgb(1, 2, 3), bg=_indexed(4), bold=True, reverse=True)
    assert reduce_style(style, "monochrome") == Style(bold=True, reverse=True)


def test_the_terminal_paints_colours_its_venue_can_show(capsys):
    display = StdioTerminal()
    display.set_caps(TerminalCaps(color_depth="256"))
    display.render_screen()
    display.board.feed_host_data(b"\x1b[38;2;255;0;0mred")
    capsys.readouterr()
    display.render_screen()
    out = capsys.readouterr().out
    assert "\x1b[38;5;196mred" in out
    assert "38;2" not in out


def test_the_terminal_paints_scrollback_in_colours_its_venue_can_show(capsys):
    display = StdioTerminal(scrollback=MemoryScrollback())
    display.set_caps(TerminalCaps(color_depth="256"))
    display.board.feed_host_data(b"\x1b[38;2;255;0;0mred\x1b[0m" + b"\r\n" * display.height)
    display.scroll_view(-1)
    capsys.readouterr()
    display.render_screen()
    assert "\x1b[38;5;196mred" in capsys.readouterr().out
