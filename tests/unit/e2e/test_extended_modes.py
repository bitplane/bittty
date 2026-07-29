"""Extended xterm private modes: storage, DECRQM self-reporting, and model gating."""

from bittty.parser import Parser
from bittty.model import VT220
from bittty import Board


class RecordingTransport:
    def __init__(self):
        self.data = []

    def write(self, data):
        self.data.append(data)

    def flush(self):
        pass


def _term(model=None):
    kwargs = {"width": 20, "height": 5}
    if model is not None:
        kwargs["model"] = model
    board = Board(**kwargs)
    transport = RecordingTransport()
    board.host.attach(transport)
    return board, Parser(board), transport


def test_extended_modes_are_stored():
    board, parser, _ = _term()
    modes = board.modes
    parser.feed("\x1b[?45h")  # reverse wraparound on
    parser.feed("\x1b[?1042h")  # bell urgency on
    assert modes.reverse_wraparound is True
    assert modes.bell_urgency is True
    parser.feed("\x1b[?45l")
    assert modes.reverse_wraparound is False


def test_allow_alt_screen_defaults_on():
    board, _, _ = _term()
    assert board.modes.allow_alt_screen is True


def test_decrqm_reports_extended_modes_on_xterm():
    board, parser, transport = _term()
    parser.feed("\x1b[?2031h")  # colour-scheme-change reporting on
    parser.feed("\x1b[?2031$p")  # DECRQM
    assert transport.data[-1] == "\x1b[?2031;1$y"  # 1 = set
    parser.feed("\x1b[?2031l")
    parser.feed("\x1b[?2031$p")
    assert transport.data[-1] == "\x1b[?2031;2$y"  # 2 = reset


def test_grapheme_mode_reports_and_changes_its_state():
    board, parser, transport = _term()
    parser.feed("\x1b[?2027$p")  # DECRQM for grapheme clustering
    assert transport.data[-1] == "\x1b[?2027;2$y"  # 2 = recognised and reset
    parser.feed("\x1b[?2027h")
    assert board.modes.grapheme_clustering is True
    parser.feed("\x1b[?2027$p")
    assert transport.data[-1] == "\x1b[?2027;1$y"
    parser.feed("\x1b[?2027l")
    assert board.modes.grapheme_clustering is False


def test_vt220_reports_xterm_era_modes_as_unrecognised():
    _, parser, transport = _term(VT220)
    parser.feed("\x1b[?2027$p")
    assert transport.data[-1] == "\x1b[?2027;0$y"
    parser.feed("\x1b[?8840$p")
    assert transport.data[-1] == "\x1b[?8840;0$y"


def test_ambiguous_width_mode_reports_its_state():
    _, parser, transport = _term()
    parser.feed("\x1b[?8840h\x1b[?8840$p")
    assert transport.data[-1] == "\x1b[?8840;1$y"
    parser.feed("\x1b[?8840l\x1b[?8840$p")
    assert transport.data[-1] == "\x1b[?8840;2$y"


def test_decrqm_now_reports_mouse_and_paste_modes():
    # These modes were previously supported but silently answered DECRQM 0.
    board, parser, transport = _term()
    parser.feed("\x1b[?1000h\x1b[?1000$p")  # mouse tracking on
    assert transport.data[-1] == "\x1b[?1000;1$y"
    parser.feed("\x1b[?1006h\x1b[?1006$p")  # SGR mouse encoding on
    assert transport.data[-1] == "\x1b[?1006;1$y"
    parser.feed("\x1b[?1002h\x1b[?1002$p")  # button-event tracking on (apply_fn-only mode)
    assert transport.data[-1] == "\x1b[?1002;1$y"
    parser.feed("\x1b[?2004$p")  # bracketed paste, currently reset
    assert transport.data[-1] == "\x1b[?2004;2$y"


def test_ansi_keyboard_action_mode():
    board, parser, _ = _term()
    parser.feed("\x1b[2h")  # KAM (non-private ANSI mode 2)
    assert board.modes.keyboard_action_mode is True
    parser.feed("\x1b[2l")
    assert board.modes.keyboard_action_mode is False
