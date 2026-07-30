"""StdioTerminal — the reference terminal, tested without a real tty.

Construction allocates no PTY and spawns no process (that happens in start_process),
so these exercise the composition and the Display hooks in isolation.
"""

from bittty import TerminalCaps
from bittty.parser import Parser
from bittty.terminals import StdioTerminal, Terminal


def test_is_a_terminal_composing_a_board():
    display = StdioTerminal()
    assert isinstance(display, Terminal)
    assert display.board is not None
    assert display.board.display.connected is True  # attached itself
    assert display.board.pty is None  # no PTY until start_process


def test_on_mouse_mode_mirrors_onto_the_host(capsys):
    display = StdioTerminal()
    display.on_mouse_mode("basic", False)
    assert "\033[?1000h\033[?1006h" in capsys.readouterr().out
    assert display.host_mouse_mode == "basic"

    display.on_mouse_mode("any", True)
    out = capsys.readouterr().out
    assert "\033[?1003h\033[?1006h" in out  # switched up to any-motion
    assert display.host_mouse_mode == "any"

    display.on_mouse_mode("off", False)
    assert "\033[?1000l" in capsys.readouterr().out  # disabled
    assert display.host_mouse_mode is None


def test_mouse_mode_flows_from_the_parser_through_the_seam(capsys):
    display = StdioTerminal()
    parser = Parser(display.board)
    parser.feed("\x1b[?1000h")  # child turns on mouse tracking
    # the modes device emits MouseModeChanged -> on_mouse_mode -> host enable printed
    assert "\033[?1000h\033[?1006h" in capsys.readouterr().out
    assert display.host_mouse_mode == "basic"


def test_on_bell_and_on_title(capsys):
    display = StdioTerminal()
    display.on_bell()
    assert "\a" in capsys.readouterr().out
    display.on_title("my title", "my title")
    assert "\033]2;my title\007" in capsys.readouterr().out


def test_ambiguous_width_mode_is_mirrored_and_deduplicated(capsys):
    display = StdioTerminal()
    display.on_ambiguous_width(2)
    display.on_ambiguous_width(2)
    display.on_ambiguous_width(1)

    assert capsys.readouterr().out == "\033[?8840h\033[?8840l"
    assert display.host_ambiguous_width == 1


def test_restore_terminal_restores_initial_ambiguous_width(capsys):
    display = StdioTerminal()
    display.initial_ambiguous_width = 2
    display.host_ambiguous_width = 1
    display.restore_terminal()

    assert "\033[?8840h" in capsys.readouterr().out
    assert display.host_ambiguous_width == 2


def test_grapheme_mode_is_mirrored_and_deduplicated(capsys):
    display = StdioTerminal()
    display.host_grapheme_mutable = True
    display.host_grapheme_clustering = False
    display.on_grapheme_clustering(True)
    display.on_grapheme_clustering(True)
    display.on_grapheme_clustering(False)

    assert capsys.readouterr().out == "\033[?2027h\033[?2027l"
    assert display.host_grapheme_clustering is False


def test_probe_synchronizes_initially_set_grapheme_mode(monkeypatch, capsys):
    display = StdioTerminal()
    monkeypatch.setattr(
        "bittty.terminals.stdio.probe_caps",
        lambda *args, **kwargs: TerminalCaps(grapheme_mode="set"),
    )

    display.probe_capabilities()

    assert capsys.readouterr().out == "\033[?2027l"
    assert display.initial_grapheme_clustering is True
    assert display.host_grapheme_clustering is False
    assert display.board.modes.get_private_mode_status(2027) == 2


def test_restore_terminal_restores_initial_grapheme_mode(capsys):
    display = StdioTerminal()
    display.host_grapheme_mutable = True
    display.initial_grapheme_clustering = True
    display.host_grapheme_clustering = False
    display.restore_terminal()

    assert "\033[?2027h" in capsys.readouterr().out
    assert display.host_grapheme_clustering is True


def test_unsupported_grapheme_mode_is_not_mirrored(capsys):
    display = StdioTerminal()
    display.set_caps(TerminalCaps(grapheme_mode="unsupported"))
    display.on_grapheme_clustering(True)

    assert "\033[?2027" not in capsys.readouterr().out
    assert display.board.modes.get_private_mode_status(2027) == 0


def test_handle_sgr_mouse_sequence_reinjects(monkeypatch):
    display = StdioTerminal()
    calls = []
    monkeypatch.setattr(display.board, "input_mouse", lambda *a, **k: calls.append((a, k)))

    assert display.handle_sgr_mouse_sequence("\033[<0;10;5M") is True  # left press at (10,5)
    assert calls == [((10, 5, 0, "press", set()), {})]

    calls.clear()
    assert display.handle_sgr_mouse_sequence("\033[<16;3;4m") is True  # ctrl release
    (x, y, button, event, mods), _ = calls[0]
    assert (x, y, button, event) == (3, 4, 0, "release") and mods == {"ctrl"}

    assert display.handle_sgr_mouse_sequence("garbage") is False  # not a mouse report


def test_shell_detection_returns_something():
    display = StdioTerminal()
    assert isinstance(display.get_default_shell(), str)


def test_lone_escape_keypress_is_flushed_next_tick():
    """A bare ESC held by the input parser must reach the child on the idle tick."""
    display = StdioTerminal()
    sent = []
    display.board.input = sent.append

    display.handle_input("\033")  # could be the start of a sequence: held
    assert sent == []

    display.flush_pending_input()  # input loop found nothing more: it was a keypress
    assert sent == ["\033"]

    display.flush_pending_input()  # idempotent when empty
    assert sent == ["\033"]


def test_control_keystrokes_pass_through():
    """Ctrl+C, Ctrl+X, Ctrl+Z (CAN/SUB) and friends reach the child intact."""
    display = StdioTerminal()
    sent = []
    display.board.input = sent.append

    for ch in ("\x03", "\x18", "\x1a", "\t", "\r", "\x7f"):
        display.handle_input(ch)
    assert sent == ["\x03", "\x18", "\x1a", "\t", "\r", "\x7f"]


def test_unknown_escape_sequences_forward_verbatim():
    """Arrow keys and other host sequences we don't intercept reach the child whole."""
    display = StdioTerminal()
    sent = []
    display.board.input = sent.append

    display.handle_input("\033[A")  # up arrow, one read
    for ch in "\033[1;5C":  # ctrl+right, dribbled char by char
        display.handle_input(ch)
    assert sent == ["\033[A", "\033[1;5C"]


def test_split_mouse_report_still_reassembles():
    """A mouse report split across reads is held and re-injected whole."""
    display = StdioTerminal()
    seen = []
    display.board.input_mouse = lambda x, y, b, e, m: seen.append((x, y, b, e))

    display.handle_input("\033[<0;3;")
    assert seen == []
    display.handle_input("4M")
    assert seen == [(3, 4, 0, "press")]


def test_host_focus_events_reach_the_board_and_child():
    """CSI I / CSI O from the host set the board's focus register."""
    display = StdioTerminal()
    typed = []
    display.board.input = typed.append

    display.handle_input("ab\033[Ocd")
    assert display.board.focused is False
    assert display.dirty is True
    assert typed == ["ab", "cd"]  # surrounding keystrokes still delivered

    display.handle_input("\033[I")
    assert display.board.focused is True


def test_render_places_the_host_hardware_cursor():
    """The chrome renders the cursor: position + show the host's own cursor."""
    display = StdioTerminal()
    display.board.parser.feed("hello")

    import io
    from contextlib import redirect_stdout

    def render():
        out = io.StringIO()
        with redirect_stdout(out):
            display.render_screen()
        return out.getvalue()

    out = render()
    assert out.endswith("\033[1;6H\033[?25h")  # after "hello", visible
    assert "\033[7m" not in out.split(f"\033[{display.height + 1}H")[0]  # no software cursor

    display.board.parser.feed("\x1b[?25l")  # child hides the cursor (DECTCEM)
    out = render()
    assert "\033[?25h" not in out


def test_handle_resize_tracks_the_outer_terminal():
    """Resize re-reads the venue's size and pushes it down to the board."""
    display = StdioTerminal()
    display.board.resize(5, 5)  # knock the board out of sync
    display.handle_resize()
    assert (display.board.width, display.board.height) == (display.width, display.height)


def test_render_repaints_only_dirty_rows():
    """Generation tracking: unchanged rows are not repainted."""
    display = StdioTerminal()
    display.board.parser.feed("hello\r\nworld")

    import io
    from contextlib import redirect_stdout

    def render():
        out = io.StringIO()
        with redirect_stdout(out):
            display.render_screen()
        return out.getvalue()

    first = render()  # first paint: everything
    assert "\033[1H" in first and "\033[2H" in first

    quiet = render()  # nothing changed: no rows repainted
    assert "\033[1H" not in quiet and "\033[2H" not in quiet

    display.board.parser.feed("\033[2;1HWORLD")  # touches row 1 only
    out = render()
    assert "\033[2H" in out and "\033[1H" not in out
