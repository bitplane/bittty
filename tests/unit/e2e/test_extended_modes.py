"""Extended private modes: implemented capabilities, honest DECRQM, and model gating."""

import pytest

from bittty import Board, TerminalCaps
from bittty.model import VT220
from bittty.parser import Parser


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


@pytest.mark.parametrize(
    "mode, attr",
    [
        (2, "ansi_mode"),
        (4, "scroll_mode"),
        (8, "auto_repeat"),
        (20, "linefeed_newline_mode"),
        (44, "margin_bell"),
        (68, "keyboard_usage_mode"),
        (80, "sixel_display_mode"),
        (1001, "mouse_highlight_tracking"),
        (1007, "alternate_scroll_mode"),
        (1016, "mouse_pixel_mode"),
        (1036, "meta_sends_escape"),
        (1042, "bell_urgency"),
        (1043, "bell_raise"),
        (1010, "scroll_on_output"),
        (1011, "scroll_on_keypress"),
        (1034, "eight_bit_input"),
        (1035, "special_modifiers"),
        (1040, "keep_selection"),
        (1041, "select_to_clipboard"),
        (1044, "reuse_clipboard"),
        (1070, "sixel_private_registers"),
        (2028, "auto_resize_mode"),
        (2031, "color_scheme_updates"),
        (7727, "application_escape"),
        (7786, "mousewheel_to_arrows"),
        (8452, "sixel_cursor_right"),
    ],
)
def test_unimplemented_private_modes_are_unrecognised_and_ignored(mode, attr):
    board, parser, transport = _term()
    before = getattr(board.modes, attr)

    parser.feed(f"\x1b[?{mode}h\x1b[?{mode}$p")

    assert getattr(board.modes, attr) == before
    assert transport.data[-1] == f"\x1b[?{mode};0$y"


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


def test_reverse_screen_and_cursor_blink_modes_report_real_state():
    board, parser, transport = _term()

    parser.feed("\x1b[?5h\x1b[?5$p\x1b[?12h\x1b[?12$p")
    assert board.modes.reverse_screen is True
    assert board.modes.cursor_blinking is True
    assert transport.data[-2:] == ["\x1b[?5;1$y", "\x1b[?12;1$y"]

    parser.feed("\x1b[?5l\x1b[?5$p\x1b[?12l\x1b[?12$p")
    assert board.modes.reverse_screen is False
    assert board.modes.cursor_blinking is False
    assert transport.data[-2:] == ["\x1b[?5;2$y", "\x1b[?12;2$y"]


@pytest.mark.parametrize(
    ("mode", "attr"),
    [
        (42, "national_charset_mode"),
        (45, "reverse_wraparound"),
        (95, "no_clear_column_mode"),
        (1005, "mouse_utf8_mode"),
        (1015, "urxvt_mouse"),
        (1039, "alt_sends_escape"),
        (1045, "extended_reverse_wraparound"),
    ],
)
def test_restored_private_modes_report_and_change_real_state(mode, attr):
    board, parser, transport = _term()

    parser.feed(f"\x1b[?{mode}$p\x1b[?{mode}h\x1b[?{mode}$p")
    assert getattr(board.modes, attr) is True
    assert transport.data[-2:] == [f"\x1b[?{mode};2$y", f"\x1b[?{mode};1$y"]

    parser.feed(f"\x1b[?{mode}l")
    assert getattr(board.modes, attr) is False


def test_printer_private_modes_report_printer_device_state():
    board, parser, transport = _term()

    parser.feed("\x1b[?18$p\x1b[?19$p")
    assert transport.data[-2:] == ["\x1b[?18;2$y", "\x1b[?19;1$y"]

    parser.feed("\x1b[?18h\x1b[?19l\x1b[?18$p\x1b[?19$p")
    assert board.printer.print_form_feed is True
    assert board.printer.print_extent is False
    assert transport.data[-2:] == ["\x1b[?18;1$y", "\x1b[?19;2$y"]


def test_delete_key_mode_reports_and_changes_structured_input():
    board, parser, transport = _term()

    parser.feed("\x1b[?1037$p")
    assert transport.data[-1] == "\x1b[?1037;2$y"

    parser.feed("\x1b[?1037h")
    board.input_key("delete")
    assert transport.data[-1] == "\x7f"

    parser.feed("\x1b[?1037l")
    board.input_key("delete")
    assert transport.data[-1] == "\x1b[3~"


def test_mode_1046_disables_alt_screen_and_gates_alt_screen_modes():
    board, parser, transport = _term()

    parser.feed("\x1b[?1049h")
    assert board.blitter.in_alt_screen is True

    parser.feed("\x1b[?1046l\x1b[?1046$p")
    assert board.modes.allow_alt_screen is False
    assert board.blitter.in_alt_screen is False
    assert transport.data[-1] == "\x1b[?1046;2$y"

    parser.feed("\x1b[?47h\x1b[?1047h\x1b[?1049h")
    assert board.blitter.in_alt_screen is False

    board.cursor.set_position(3, 2)
    parser.feed("\x1b[?1048h")
    board.cursor.set_position(9, 4)
    parser.feed("\x1b[?1048l")
    assert (board.cursor.x, board.cursor.y) == (9, 4)

    parser.feed("\x1b[?1046h\x1b[?1046$p\x1b[?1047h")
    assert board.modes.allow_alt_screen is True
    assert transport.data[-1] == "\x1b[?1046;1$y"
    assert board.blitter.in_alt_screen is True


def test_destination_can_hide_grapheme_mode():
    board, parser, transport = _term()
    board.set_caps(TerminalCaps(grapheme_mode="unsupported"))

    parser.feed("\x1b[?2027h\x1b[?2027$p")

    assert board.modes.grapheme_clustering is False
    assert transport.data[-1] == "\x1b[?2027;0$y"


def test_mutable_destination_keeps_live_grapheme_mode_status():
    board, parser, transport = _term()
    board.set_caps(TerminalCaps(grapheme_mode="reset"))

    parser.feed("\x1b[?2027h\x1b[?2027$p")

    assert board.modes.grapheme_clustering is True
    assert transport.data[-1] == "\x1b[?2027;1$y"


def test_permanently_set_grapheme_mode_survives_reset():
    board, parser, transport = _term()
    board.set_caps(TerminalCaps(grapheme_mode="permanently-set"))

    parser.feed("\x1b[?2027l\x1bc\x1b[?2027$p")

    assert board.modes.grapheme_clustering is True
    assert transport.data[-1] == "\x1b[?2027;3$y"


def test_permanently_reset_grapheme_mode_ignores_set():
    board, parser, transport = _term()
    board.set_caps(TerminalCaps(grapheme_mode="permanently-reset"))

    parser.feed("\x1b[?2027h\x1b[?2027$p")

    assert board.modes.grapheme_clustering is False
    assert transport.data[-1] == "\x1b[?2027;4$y"


def test_destination_caps_cannot_add_grapheme_mode_to_old_model():
    board, parser, transport = _term(VT220)
    board.set_caps(TerminalCaps(grapheme_mode="set"))

    parser.feed("\x1b[?2027$p")

    assert transport.data[-1] == "\x1b[?2027;0$y"


def test_vt220_reports_xterm_era_modes_as_unrecognised():
    _, parser, transport = _term(VT220)
    parser.feed("\x1b[?18$p\x1b[?19$p")
    assert transport.data[-2:] == ["\x1b[?18;2$y", "\x1b[?19;1$y"]
    parser.feed("\x1b[?42$p")
    assert transport.data[-1] == "\x1b[?42;2$y"
    for mode in (45, 95, 1005, 1015, 1037, 1039, 1045):
        parser.feed(f"\x1b[?{mode}$p")
        assert transport.data[-1] == f"\x1b[?{mode};0$y"
    parser.feed("\x1b[?5$p")
    assert transport.data[-1] == "\x1b[?5;2$y"
    parser.feed("\x1b[?12$p")
    assert transport.data[-1] == "\x1b[?12;0$y"
    parser.feed("\x1b[?1046$p")
    assert transport.data[-1] == "\x1b[?1046;0$y"
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


@pytest.mark.parametrize("mode, attr", [(2, "keyboard_action_mode"), (12, "local_echo")])
def test_unimplemented_ansi_modes_are_unrecognised_and_ignored(mode, attr):
    board, parser, transport = _term()
    before = getattr(board.modes, attr)

    parser.feed(f"\x1b[{mode}h\x1b[{mode}$p")

    assert getattr(board.modes, attr) == before
    assert transport.data[-1] == f"\x1b[{mode};0$y"
