"""Emulator personalities grabbed from real terminfo + a live tmux DA query."""

from bittty import constants
from bittty.parser import Parser
from bittty.personality import GNOME, SCREEN, TMUX, URXVT, XTERM, get_personality
from bittty.terminal import Terminal


class RecordingTransport:
    def __init__(self):
        self.data = []

    def write(self, data):
        self.data.append(data)

    def flush(self):
        pass


def _term(personality):
    terminal = Terminal(width=80, height=24, personality=personality)
    transport = RecordingTransport()
    terminal.board.host.attach(transport)
    return terminal, Parser(terminal.board), transport


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


def test_screen_and_urxvt_secondary_da_types():
    _, parser, t = _term(SCREEN)
    parser.feed("\x1b[>c")
    assert t.data == ["\x1b[>83;0;0c"]  # 'S'
    _, parser, t = _term(URXVT)
    parser.feed("\x1b[>c")
    assert t.data == ["\x1b[>85;0;0c"]  # 'U'


def test_screen_function_keys_use_ss3_like_xterm():
    terminal, _, transport = _term(SCREEN)
    terminal.input_fkey(1)  # F1
    assert transport.data == [f"{constants.ESC}OP"]


def test_urxvt_function_keys_use_tilde_codes():
    terminal, _, transport = _term(URXVT)
    terminal.input_fkey(1)  # F1 — rxvt sends CSI 11~, not SS3
    assert transport.data == [f"{constants.ESC}[11~"]


def test_screen_home_key_is_vt220_style():
    terminal, _, transport = _term(SCREEN)
    terminal.input_key("home")  # screen: CSI 1~ (not xterm's CSI H)
    assert transport.data == [f"{constants.ESC}[1~"]


def test_urxvt_home_key():
    terminal, _, transport = _term(URXVT)
    terminal.input_key("home")  # rxvt: CSI 7~
    assert transport.data == [f"{constants.ESC}[7~"]


def test_xterm_now_encodes_the_editing_keypad():
    terminal, _, transport = _term(XTERM)
    terminal.input_key("delete")  # newly added to XTERM_KEYMAP from terminfo
    assert transport.data == [f"{constants.ESC}[3~"]


def test_get_personality_resolves_term_names():
    assert get_personality("tmux-256color") is TMUX
    assert get_personality("screen-256color") is SCREEN
    assert get_personality("rxvt-unicode-256color") is URXVT
    assert get_personality("xterm-256color") is XTERM
    assert get_personality("gnome-256color") is GNOME


def test_get_personality_falls_back_through_prefixes():
    assert get_personality("xterm-kitty") is XTERM  # unknown suffix -> nearest family
    assert get_personality("totally-unknown") is XTERM  # -> default
    assert get_personality("") is XTERM
    assert get_personality(None) is XTERM
