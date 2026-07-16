"""Extended SGR: double/styled underline, overline, underline colour, colon forms."""

from bittty.style import Color, parse_sgr_sequence, style_to_ansi


def test_double_underline():
    style = parse_sgr_sequence("\x1b[21m")
    assert style.underline is True
    assert style.underline_style == "double"


def test_colon_underline_styles():
    assert parse_sgr_sequence("\x1b[4:3m").underline_style == "curly"
    assert parse_sgr_sequence("\x1b[4:2m").underline_style == "double"
    assert parse_sgr_sequence("\x1b[4:1m").underline is True
    assert parse_sgr_sequence("\x1b[4:1m").underline_style is None  # single
    assert parse_sgr_sequence("\x1b[4:0m").underline is False


def test_overline():
    assert parse_sgr_sequence("\x1b[53m").overline is True
    assert parse_sgr_sequence("\x1b[53;55m").overline is False


def test_underline_colour_semicolon_and_colon():
    assert parse_sgr_sequence("\x1b[58;5;9m").underline_color == Color("indexed", 9)
    assert parse_sgr_sequence("\x1b[58;2;10;20;30m").underline_color == Color("rgb", (10, 20, 30))
    assert parse_sgr_sequence("\x1b[58:2::10:20:30m").underline_color == Color("rgb", (10, 20, 30))
    assert parse_sgr_sequence("\x1b[59m").underline_color == Color("default")


def test_colon_form_truecolor_and_indexed():
    assert parse_sgr_sequence("\x1b[38:2:255:0:0m").fg == Color("rgb", (255, 0, 0))
    assert parse_sgr_sequence("\x1b[38:5:200m").fg == Color("indexed", 200)
    assert parse_sgr_sequence("\x1b[48:2:1:2:3m").bg == Color("rgb", (1, 2, 3))


def test_extended_attributes_round_trip():
    for seq in ("\x1b[21m", "\x1b[4:3m", "\x1b[53m", "\x1b[58;2;1;2;3m", "\x1b[38:5:200m"):
        style = parse_sgr_sequence(seq)
        assert parse_sgr_sequence(style_to_ansi(style)) == style
