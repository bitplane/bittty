"""The VT5xx character sets: Greek, Hebrew, Russian, SCS and Turkish national replacement sets,
and DEC Cyrillic and the DEC Greek, Hebrew and Turkish supplementals.

Captured from xterm 407 at its VT525 level (decTerminalID 525); each row is what the GL
codes 2/1-7/14 show with the set designated as G0 (the national sets in national mode).
"""

import pytest

from bittty import Board, KeyEvent, MemoryConnection
from bittty.model import VT510, XTERM

GL = "".join(chr(c) for c in range(0x21, 0x7F))

SHOWN = {
    ('">', True): "!\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`ΑΒΓΔΕΖΗΘΙΚΛΜΝΧΟΠΡΣΤΥΦΞΨΩ␦␦{|}~",
    ("%=", True): "!\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_אבגדהוזחטיךכלםמןנסעףפץצקרשת{|}~",
    ("&5", True): "!\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_ЮАБЦДЕФГХИЙКЛМНОПЯРСТУЖВЬЫЗШЭЩЧ",
    ("%3", True): "!\"#$%&'()*+,-./0123456789:;<=>?ŽABCDEFGHIJKLMNOPQRSTUVWXYZŠĐĆČ_žabcdefghijklmnopqrstuvwxyzšđćč",
    ("%2", True): "!\"#$%ğ'()*+,-./0123456789:;<=>?İABCDEFGHIJKLMNOPQRSTUVWXYZŞÖÇÜ_Ğabcdefghijklmnopqrstuvwxyzşöçü",
    ("&4", False): "␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦юабцдефгхийклмнопярстужвьызшэщчъЮАБЦДЕФГХИЙКЛМНОПЯРСТУЖВЬЫЗШЭЩЧ",
    ('"?', False): "¡¢£␦¥␦§¤©ª«␦␦␦␦°±²³␦µ¶·␦¹º»¼½␦¿ϊΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟ␦ΠΡΣΤΥΦΧΨΩάέήί␦όϋαβγδεζηθικλμνξο␦πρστυφχψωςύώ΄␦",
    ('"4', False): "¡¢£␦¥␦§¨©×«␦␦␦␦°±²³␦µ¶·␦¹÷»¼½␦¿␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦␦אבגדהוזחטיךכלםמןנסעףפץצקרשת␦␦␦␦",
    ("%0", False): "¡¢£␦¥␦§¨©ª«␦␦İ␦°±²³␦µ¶·␦¹º»¼½ı¿ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏĞÑÒÓÔÕÖŒØÙÚÛÜŸŞßàáâãäåæçèéêëìíîïğñòóôõöœøùúûüÿş",
}


@pytest.mark.parametrize(("designation", "shown"), SHOWN.items())
def test_vt5xx_sets(designation, shown):
    designator, national = designation
    board = Board(width=100, height=2, model=VT510)
    board.feed_host_data(("\x1b[?42h" if national else "") + f"\x1b({designator}" + GL)
    assert board.blitter.current_page.get_line_text(0).rstrip() == shown


@pytest.mark.parametrize("designator", ['">', "%=", "&5", "%3", "%2"])
def test_national_sets_need_national_mode(designator):
    board = Board(width=100, height=2, model=VT510)
    board.feed_host_data(f"\x1b({designator}" + GL)
    assert board.blitter.current_page.get_line_text(0).rstrip() == GL


def test_xterm_at_its_vt4xx_level_has_none_of_them():
    board = Board(width=100, height=2, model=XTERM)
    board.feed_host_data("\x1b(&4" + GL)
    assert board.blitter.current_page.get_line_text(0).rstrip() == GL


@pytest.mark.parametrize("designator", ['"?', '"4', "%0", "&4"])
def test_they_can_be_the_user_preferred_set(designator):
    board = Board(width=100, height=2, model=VT510)
    wire = MemoryConnection()
    board.host.attach(wire)
    board.feed_host_data(f"\x1bP0!u{designator}\x1b\\\x1b[&u\x1b(<" + GL)
    assert wire.data == [f"\x1bP0!u{designator}\x1b\\"]
    assert board.blitter.current_page.get_line_text(0).rstrip() == SHOWN[(designator, False)]


@pytest.mark.parametrize(
    ("language", "typed", "sent"), [(22, "Α", "a"), (19, "א", "`"), (39, "Ю", "`"), (29, "ş", "{")]
)
def test_their_keyboards_send_them_in_national_mode(language, typed, sent):
    board = Board(model=VT510)
    wire = MemoryConnection()
    board.host.attach(wire)
    board.feed_host_data(f"\x1b[;{language} }}\x1b[?42h")
    board.input_key_event(KeyEvent("a", text=typed))
    assert wire.text == sent
