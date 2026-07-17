"""StdioTerminal — the reference terminal, tested without a real tty.

Construction allocates no PTY and spawns no process (that happens in start_process),
so these exercise the composition and the Display hooks in isolation.
"""

from bittty.terminals import StdioTerminal, Terminal
from bittty.parser import Parser


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
    parser = Parser(display.board.board)
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
    """A bare ESC held back by the mouse-prefix buffer must reach the child."""
    display = StdioTerminal()
    sent = []
    display.board.input = sent.append

    display.handle_input("\033")  # could be the start of a mouse report: buffered
    assert sent == []
    assert display.input_sequence_buffer == "\033"

    display.flush_pending_input()  # input loop found nothing more: it was a keypress
    assert sent == ["\033"]
    assert display.input_sequence_buffer == ""

    display.flush_pending_input()  # idempotent when empty
    assert sent == ["\033"]


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


def test_render_hides_software_cursor_when_unfocused(capsys):
    display = StdioTerminal()
    display.board.parser.feed("hello")

    def pane_area():
        # Everything before the status line (which uses reverse video itself).
        out = capsys.readouterr().out
        return out.split(f"\033[{display.height + 1}H")[0]

    display.board.focused = True
    display.render_screen()
    assert "\033[7m" in pane_area()  # reverse-video cursor cell

    display.board.focused = False
    display.render_screen()
    assert "\033[7m" not in pane_area()


def test_handle_resize_tracks_the_outer_terminal():
    """Resize re-reads the venue's size and pushes it down to the board."""
    display = StdioTerminal()
    display.board.resize(5, 5)  # knock the board out of sync
    display.handle_resize()
    assert (display.board.width, display.board.height) == (display.width, display.height)
