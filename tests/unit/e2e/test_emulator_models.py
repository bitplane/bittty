"""Emulator models grabbed from real terminfo + a live tmux DA query."""

from bittty import Board, MemoryConnection, constants
from bittty.model import BITTTY, GNOME, KITTY, SCREEN, TMUX, URXVT, XTERM, get_model
from bittty.parser import Parser


def _term(model):
    board = Board(width=80, height=24, model=model)
    transport = MemoryConnection()
    board.host.attach(transport)
    return board, Parser(board), transport


def test_tmux_reports_its_live_device_attributes():
    _, parser, transport = _term(TMUX)
    parser.feed("\x1b[c")  # DA1 — verified against a running tmux
    parser.feed("\x1b[>c")  # DA2 — type 84 = 'T'
    assert transport.data == ["\x1b[?1;2;4c", "\x1b[>84;0;0c"]


def test_gnome_reports_its_live_device_attributes():
    _, parser, transport = _term(GNOME)
    parser.feed("\x1b[c")  # DA1 — verified against gnome-terminal (VTE 0.84)
    parser.feed("\x1b[>c")  # DA2 — type 61, firmware 8400 = VTE version
    assert transport.data == ["\x1b[?61;1;21;22;28c", "\x1b[>61;8400;1c"]


def test_kitty_reports_its_live_device_attributes():
    _, parser, transport = _term(KITTY)
    parser.feed("\x1b[c")  # DA1 — captured from kitty
    parser.feed("\x1b[>c")  # DA2 — firmware 4000 = kitty 0.40
    assert transport.data == ["\x1b[?62;52;c", "\x1b[>1;4000;45c"]


def test_screen_and_urxvt_secondary_da_types():
    _, parser, t = _term(SCREEN)
    parser.feed("\x1b[>c")
    assert t.data == ["\x1b[>83;0;0c"]  # 'S'
    _, parser, t = _term(URXVT)
    parser.feed("\x1b[>c")
    assert t.data == ["\x1b[>85;0;0c"]  # 'U'


def test_screen_function_keys_use_ss3_like_xterm():
    board, _, transport = _term(SCREEN)
    board.input_fkey(1)  # F1
    assert transport.data == [f"{constants.ESC}OP"]


def test_urxvt_function_keys_use_tilde_codes():
    board, _, transport = _term(URXVT)
    board.input_fkey(1)  # F1 — rxvt sends CSI 11~, not SS3
    assert transport.data == [f"{constants.ESC}[11~"]


def test_screen_home_key_is_vt220_style():
    board, _, transport = _term(SCREEN)
    board.input_key("home")  # screen: CSI 1~ (not xterm's CSI H)
    assert transport.data == [f"{constants.ESC}[1~"]


def test_urxvt_home_key():
    board, _, transport = _term(URXVT)
    board.input_key("home")  # rxvt: CSI 7~
    assert transport.data == [f"{constants.ESC}[7~"]


def test_xterm_now_encodes_the_editing_keypad():
    board, _, transport = _term(XTERM)
    board.input_key("delete")  # newly added to XTERM_KEYMAP from terminfo
    assert transport.data == [f"{constants.ESC}[3~"]


def test_get_model_resolves_term_names():
    assert get_model("tmux-256color") is TMUX
    assert get_model("screen-256color") is SCREEN
    assert get_model("rxvt-unicode-256color") is URXVT
    assert get_model("xterm-256color") is XTERM
    assert get_model("gnome-256color") is GNOME
    assert get_model("xterm-kitty") is KITTY  # kitty sets a distinctive TERM


def test_get_model_falls_back_through_prefixes():
    assert get_model("xterm-ghostty") is XTERM  # unknown suffix -> nearest family
    assert get_model("totally-unknown") is BITTTY  # -> native default
    assert get_model("") is BITTTY
    assert get_model(None) is BITTTY
