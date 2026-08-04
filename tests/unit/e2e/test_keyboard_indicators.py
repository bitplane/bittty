"""Keyboard indicator LEDs: DECLL and modes 108 (DECNUMLK), 109 (DECCAPSLK), 110 (DECKLHIM)."""

from bittty import Board, MemoryConnection
from bittty.model import LINUX, VT510, XTERM
from bittty.parser import Parser
from bittty.present import KeyboardIndicatorChanged


class Recorder:
    def __init__(self):
        self.events = []

    def present(self, event):
        self.events.append(event)


def _term(*, model=None):
    board = Board(width=20, height=4, model=model)
    transport = MemoryConnection()
    recorder = Recorder()
    board.host.attach(transport)
    board.display.attach(recorder)
    return board, Parser(board), transport, recorder


def _lights(recorder):
    return [e for e in recorder.events if isinstance(e, KeyboardIndicatorChanged)]


# --- the modes exist, report, and default to reset --- #


def test_indicator_modes_report_reset_by_default_and_set_when_set():
    for model in (VT510, None):  # None = the default bittty model
        _board, parser, transport, _recorder = _term(model=model)
        parser.feed("\x1b[?108$p\x1b[?109$p\x1b[?110$p")
        assert transport.data == ["\x1b[?108;2$y", "\x1b[?109;2$y", "\x1b[?110;2$y"]

        transport.data.clear()
        parser.feed("\x1b[?108h\x1b[?108$p")
        assert transport.data == ["\x1b[?108;1$y"]


def test_xterm_has_decll_but_not_the_modes():
    _board, parser, transport, recorder = _term(model=XTERM)
    parser.feed("\x1b[?108$p")
    assert transport.data == ["\x1b[?108;0$y"]  # not in the repertoire

    parser.feed("\x1b[1q")  # ...but DECLL functions, unconditionally
    assert _lights(recorder) == [KeyboardIndicatorChanged(True, False, False)]


def test_a_terminal_without_leds_recognises_nothing_and_never_speaks():
    board, parser, transport, recorder = _term(model=LINUX)
    parser.feed("\x1b[1q\x1b[?108h\x1b[?108$p")
    assert "DECLL" not in board.registry
    assert transport.data == ["\x1b[?108;0$y"]
    assert _lights(recorder) == []


# --- keyboard-state display (DECKLHIM reset) --- #


def test_lock_modes_drive_the_leds_while_klhim_is_reset():
    _board, parser, _transport, recorder = _term()
    parser.feed("\x1b[?108h")
    parser.feed("\x1b[?109h")
    assert _lights(recorder) == [
        KeyboardIndicatorChanged(True, False, False),
        KeyboardIndicatorChanged(True, True, False),
    ]


# --- host display (DECKLHIM set) --- #


def test_decll_drives_the_leds_while_klhim_is_set():
    _board, parser, _transport, recorder = _term()
    parser.feed("\x1b[?110h")
    parser.feed("\x1b[1q")
    parser.feed("\x1b[1;2q")  # num already lit; caps joins it
    parser.feed("\x1b[21q")  # extinguish num, caps stays
    parser.feed("\x1b[0q")  # clear all
    assert _lights(recorder) == [
        KeyboardIndicatorChanged(True, False, False),
        KeyboardIndicatorChanged(True, True, False),
        KeyboardIndicatorChanged(False, True, False),
        KeyboardIndicatorChanged(False, False, False),
    ]


def test_multi_parameter_decll_lights_several_in_one_sequence():
    _board, parser, _transport, recorder = _term()
    parser.feed("\x1b[?110h\x1b[1;3q")
    assert _lights(recorder) == [KeyboardIndicatorChanged(True, False, True)]


def test_klhim_reveals_indications_loaded_while_it_was_reset():
    """The VT510 gate: DECLL does not function until DECKLHIM is set.

    The loaded bits are stored, not discarded — the mode selects what the LEDs
    display, so setting it afterwards reveals them in one event.
    """
    _board, parser, _transport, recorder = _term()
    parser.feed("\x1b[1q")  # klhim reset: display unchanged, no event
    assert _lights(recorder) == []

    parser.feed("\x1b[?110h")
    assert _lights(recorder) == [KeyboardIndicatorChanged(True, False, False)]


def test_klhim_switches_between_the_two_displays():
    _board, parser, _transport, recorder = _term()
    parser.feed("\x1b[?108h")  # keyboard state: num
    parser.feed("\x1b[?110h\x1b[2q")  # host state: dark until caps is loaded
    parser.feed("\x1b[?110l")  # back to keyboard state
    assert _lights(recorder) == [
        KeyboardIndicatorChanged(True, False, False),
        KeyboardIndicatorChanged(False, False, False),  # host bits are empty at the flip
        KeyboardIndicatorChanged(False, True, False),
        KeyboardIndicatorChanged(True, False, False),
    ]


# --- edges and resets --- #


def test_a_display_preserving_change_emits_nothing():
    _board, parser, _transport, recorder = _term()
    parser.feed("\x1b[?110h\x1b[1q")
    events = len(_lights(recorder))
    parser.feed("\x1b[1q")  # already lit
    parser.feed("\x1b[22q")  # already dark
    assert len(_lights(recorder)) == events


def test_ris_clears_loaded_bits_and_mode_flags():
    board, parser, _transport, recorder = _term()
    parser.feed("\x1b[?110h\x1b[1;2;3q")
    parser.feed("\x1bc")
    assert _lights(recorder)[-1] == KeyboardIndicatorChanged(False, False, False)
    assert board.keyboard.indicator_lights() == (False, False, False)
    assert (board.keyboard.led_num, board.keyboard.led_caps, board.keyboard.led_scroll) == (False, False, False)


def test_null_parameters_read_as_the_clear_default():
    _board, parser, _transport, recorder = _term()
    parser.feed("\x1b[?110h\x1b[1q")
    parser.feed("\x1b[;q")  # (None, None) -> 0: clear all
    assert _lights(recorder)[-1] == KeyboardIndicatorChanged(False, False, False)
