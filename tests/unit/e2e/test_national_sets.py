"""National replacement character sets (DECNRCM set), captured from xterm 407.

Each row is what the replaceable positions # $ @ [ \\ ] ^ _ ` { | } ~ show. Dutch [ and |
are DEC's ĳ and ƒ, which xterm's 8-bit tables cannot hold and leave as the ASCII bytes.
"""

import pytest

from bittty import Board
from bittty.model import XTERM

POSITIONS = "#$@[\\]^_`{|}~"


@pytest.mark.parametrize(
    ("designators", "shown"),
    [
        ("A", "£$@[\\]^_`{|}~"),  # United Kingdom
        ("4", "£$¾ĳ½|^_`¨ƒ¼´"),  # Dutch
        ("C5", "#$@ÄÖÅÜ_éäöåü"),  # Finnish
        ("Rf", "£$à°ç§^_`éùè¨"),  # French
        ("Q9", "#$àâçêî_ôéùèû"),  # French Canadian
        ("K", "#$§ÄÖÜ^_`äöüß"),  # German
        ("Y", "£$§°çé^_ùàòèì"),  # Italian
        ("E6`", "#$ÄÆØÅÜ_äæøåü"),  # Norwegian/Danish
        (["%6"], "#$@ÃÇÕ^_`ãçõ~"),  # Portuguese
        ("Z", "£$§¡Ñ¿^_`°ñç~"),  # Spanish
        ("H7", "#$ÉÄÖÅÜ_éäöåü"),  # Swedish
        ("=", "ù$àéçêîèôäöüû"),  # Swiss
    ],
)
def test_national_replacement_sets(designators, shown):
    for designator in designators:
        board = Board(width=20, height=2, model=XTERM)
        board.feed_host_data(f"\x1b[?42h\x1b({designator}{POSITIONS}")
        assert board.blitter.current_page.get_line_text(0).rstrip() == shown, designator
