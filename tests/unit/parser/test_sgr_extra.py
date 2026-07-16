"""SGR gaps: font selection (10-19), fraktur (20), framed/encircled (51/52/54), ideogram (60-65)."""

from bittty.style import Style, parse_sgr_sequence, style_to_ansi


def _parse(params):
    return parse_sgr_sequence(f"\x1b[{params}m")


def test_font_selection():
    assert _parse("13").font == 3  # alternate font 3
    assert _parse("10").font == 0  # primary font
    assert _parse("19").font == 9


def test_font_roundtrips():
    assert style_to_ansi(Style(font=3)) == "\x1b[13m"
    assert style_to_ansi(Style(font=0)) == "\x1b[10m"


def test_fraktur_set_and_reset_with_italic():
    assert _parse("20").fraktur is True
    # SGR 23 turns off italic *and* fraktur
    s = _parse("3;20")
    assert s.italic is True and s.fraktur is True
    off = s.merge(_parse("23"))
    assert off.italic is False and off.fraktur is False


def test_framed_and_encircled():
    assert _parse("51").framed is True
    assert _parse("52").encircled is True
    both = _parse("51;52")
    cleared = both.merge(_parse("54"))  # 54 turns off both
    assert cleared.framed is False and cleared.encircled is False


def test_framed_roundtrips():
    assert style_to_ansi(Style(framed=True)) == "\x1b[51m"
    assert style_to_ansi(Style(encircled=True)) == "\x1b[52m"


def test_ideogram_attributes():
    assert _parse("60").ideogram == "underline"
    assert _parse("62").ideogram == "overline"
    assert _parse("64").ideogram == "stress"
    assert _parse("65").ideogram == "none"  # reset


def test_ideogram_roundtrips():
    assert style_to_ansi(Style(ideogram="double_underline")) == "\x1b[61m"
    assert style_to_ansi(Style(ideogram="none")) == "\x1b[65m"


def test_combined_sgr_still_parses_colours():
    # the new codes must not disturb existing colour/attribute handling
    s = _parse("1;51;38;5;42;60")
    assert s.bold is True
    assert s.framed is True
    assert s.fg.mode == "indexed" and s.fg.value == 42
    assert s.ideogram == "underline"
