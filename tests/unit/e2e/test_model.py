"""Model-driven behaviour: the same board answers as different terminals."""

from bittty import constants
from bittty.parser import Parser
from bittty.model import LINUX, VT100, VT220, XTERM
from bittty.style import Color
from bittty import Board


class RecordingTransport:
    def __init__(self):
        self.data = []

    def write(self, data):
        self.data.append(data)

    def flush(self):
        pass


def _replies(model, sequence):
    kwargs = {"width": 80, "height": 24}
    if model is not None:
        kwargs["model"] = model
    terminal = Board(**kwargs)
    transport = RecordingTransport()
    terminal.board.host.attach(transport)
    Parser(terminal.board).feed(sequence)
    return transport.data


def test_primary_da_response_differs_by_model():
    assert _replies(XTERM, "\x1b[c") == ["\033[?62;1;6;8;9;15;18;21;22;23c"]
    assert _replies(VT100, "\x1b[c") == ["\033[?1;2c"]
    assert _replies(VT220, "\x1b[c") == ["\033[?62;1;2;6;8;9c"]


def test_vt100_does_not_answer_secondary_da():
    # Secondary DA was introduced with the VT220; a VT100 must stay silent.
    assert _replies(VT100, "\x1b[>c") == []
    assert _replies(XTERM, "\x1b[>c") == ["\033[>1;10;0c"]


def test_default_model_is_xterm():
    assert _replies(None, "\x1b[c") == ["\033[?62;1;6;8;9;15;18;21;22;23c"]
    assert Board().model.name == "xterm"


def test_model_can_omit_a_mode():
    # xterm supports bracketed paste (private mode 2004); a VT100 does not, so
    # the same DECSET sequence is a no-op there.
    xterm = Board(width=80, height=24)
    Parser(xterm.board).feed("\x1b[?2004h")
    assert xterm.board.modes.bracketed_paste is True

    vt100 = Board(width=80, height=24, model=VT100)
    Parser(vt100.board).feed("\x1b[?2004h")
    assert vt100.board.modes.bracketed_paste is False


def test_model_charset_repertoire():
    # DEC Supplemental (designator "<") arrived with the VT220; a VT100 ignores
    # the designation and stays on ASCII, while xterm accepts it.
    xterm = Board(width=80, height=24)
    Parser(xterm.board).feed("\x1b(<")  # SCS G0 -> DEC Supplemental
    assert xterm.board.charset.g0_charset == "<"

    vt100 = Board(width=80, height=24, model=VT100)
    Parser(vt100.board).feed("\x1b(<")
    assert vt100.board.charset.g0_charset == "B"  # unsupported -> ignored

    # ...but a charset the VT100 does know still designates.
    Parser(vt100.board).feed("\x1b(0")  # DEC Special Graphics
    assert vt100.board.charset.g0_charset == "0"


def _fkey(model, num, modifier=constants.KEY_MOD_NONE):
    kwargs = {"width": 80, "height": 24}
    if model is not None:
        kwargs["model"] = model
    terminal = Board(**kwargs)
    transport = RecordingTransport()
    terminal.board.host.attach(transport)
    terminal.input_fkey(num, modifier)
    return transport.data


def _key(model, char, modifier=constants.KEY_MOD_NONE):
    kwargs = {"width": 80, "height": 24}
    if model is not None:
        kwargs["model"] = model
    terminal = Board(**kwargs)
    transport = RecordingTransport()
    terminal.board.host.attach(transport)
    terminal.input_key(char, modifier)
    return transport.data


def test_function_keys_are_model_specific():
    # xterm has F5; a VT100 has only PF1-PF4, so F5 sends nothing.
    assert _fkey(XTERM, 5) == ["\x1b[15~"]
    assert _fkey(VT100, 5) == []
    assert _fkey(VT100, 1) == ["\x1bOP"]  # PF1

    # xterm folds modifiers into the sequence; a VT100 has no modifier encoding.
    assert _fkey(XTERM, 1, constants.KEY_MOD_SHIFT) == ["\x1b[1;2P"]
    assert _fkey(VT100, 1, constants.KEY_MOD_SHIFT) == ["\x1bOP"]


def test_vt220_is_distinct_across_every_axis():
    # Identity: VT220 primary DA, and unlike a VT100 it answers secondary DA.
    assert _replies(VT220, "\x1b[c") == ["\033[?62;1;2;6;8;9c"]
    assert _replies(VT220, "\x1b[>c") == ["\033[>1;10;0c"]

    vt220 = Board(width=80, height=24, model=VT220)
    parser = Parser(vt220.board)

    # Modes: the VT220 predates mouse tracking, so DECSET 1000 is a no-op.
    parser.feed("\x1b[?1000h")
    assert vt220.board.modes.mouse_tracking is False

    # Charsets: it knows DEC Supplemental ("<", a VT220 addition) but not DEC
    # Technical (">", a later set).
    parser.feed("\x1b(<")
    assert vt220.board.charset.g0_charset == "<"
    parser.feed("\x1b)>")  # DEC Technical -> ignored
    assert vt220.board.charset.g1_charset == "B"

    # Colour: a base VT220 is monochrome, so SGR colour is dropped.
    parser.feed("\x1b[31m")
    assert vt220.board.style.current.fg is None

    # Keyboard: it has F6 (a VT100 lacks it) but not F5 (xterm has it), and its
    # Home key is the editing keypad's Find (ESC [ 1 ~), not xterm's ESC [ H.
    assert _fkey(VT220, 6) == ["\x1b[17~"]
    assert _fkey(VT220, 5) == []
    assert _key(VT220, "home") == ["\x1b[1~"]


def test_linux_console_is_distinct():
    # Identity: the linux console answers primary DA as a VT102 and stays silent
    # on secondary DA.
    assert _replies(LINUX, "\x1b[c") == ["\033[?6c"]
    assert _replies(LINUX, "\x1b[>c") == []

    # Keyboard: the console's signature F1-F5 as ESC [ [ A .. E.
    assert _fkey(LINUX, 1) == ["\x1b[[A"]
    assert _fkey(LINUX, 5) == ["\x1b[[E"]
    assert _fkey(LINUX, 6) == ["\x1b[17~"]

    # Palette: the console ships the VGA colours, not xterm's.
    linux = Board(width=80, height=24, model=LINUX)
    assert linux.board.palette.resolve(Color("indexed", 1)) == (170, 0, 0)  # VGA red
    assert Board().board.palette.resolve(Color("indexed", 1)) == (205, 0, 0)  # xterm red


def test_numpad_uses_the_keymap():
    terminal = Board(width=80, height=24)
    transport = RecordingTransport()
    terminal.board.host.attach(transport)

    terminal.input_numpad_key("5")  # numeric keypad (default) sends the digit
    assert transport.data == ["5"]

    Parser(terminal.board).feed("\x1b=")  # DECKPAM -> application keypad
    transport.data.clear()
    terminal.input_numpad_key("5")
    assert transport.data == ["\x1bOu"]


def test_navigation_keys_are_model_specific():
    # xterm has Home/End; a VT100 keyboard has neither, so they send nothing.
    assert _key(XTERM, "home") == ["\x1b[H"]
    assert _key(VT100, "home") == []
    # Arrow keys exist on both, but a VT100 has no modifier encoding.
    assert _key(XTERM, "up", constants.KEY_MOD_SHIFT) == ["\x1b[1;2A"]
    assert _key(VT100, "up", constants.KEY_MOD_SHIFT) == ["\x1b[A"]


def test_monochrome_model_ignores_sgr_colour():
    from bittty.style import Color

    # xterm keeps the colour; a monochrome VT100 drops it but keeps bold.
    xterm = Board(width=80, height=24)
    Parser(xterm.board).feed("\x1b[31;1m")
    assert xterm.board.style.current.fg == Color("indexed", 1)
    assert xterm.board.style.current.bold is True

    vt100 = Board(width=80, height=24, model=VT100)
    Parser(vt100.board).feed("\x1b[31;1m")
    assert vt100.board.style.current.fg is None  # colour ignored
    assert vt100.board.style.current.bold is True  # video attributes still apply


def test_decrqm_reports_unrecognised_for_omitted_mode():
    # DECRQM for a mode the model lacks must answer "not recognised" (0).
    transport_xterm = RecordingTransport()
    xterm = Board(width=80, height=24)
    xterm.board.host.attach(transport_xterm)
    Parser(xterm.board).feed("\x1b[?2028$p")  # DECRQM for auto-resize mode
    assert transport_xterm.data == ["\033[?2028;2$y"]  # 2 = reset (recognised)

    transport_vt100 = RecordingTransport()
    vt100 = Board(width=80, height=24, model=VT100)
    vt100.board.host.attach(transport_vt100)
    Parser(vt100.board).feed("\x1b[?2028$p")
    assert transport_vt100.data == ["\033[?2028;0$y"]  # 0 = not recognised
