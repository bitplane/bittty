"""Phase 3: PassthroughDisplay — the reference frontend, tested without a real tty.

Construction allocates no PTY and spawns no process (that happens in start_process),
so these exercise the composition and the Display hooks in isolation.
"""

from bittty.frontends import Display
from bittty.frontends.passthrough import PassthroughDisplay
from bittty.parser import Parser


def test_is_a_display_composing_a_terminal():
    display = PassthroughDisplay()
    assert isinstance(display, Display)
    assert display.terminal is not None
    assert display.terminal.board.display.connected is True  # attached itself
    assert display.terminal.pty is None  # no PTY until start_process


def test_on_mouse_mode_mirrors_onto_the_host(capsys):
    display = PassthroughDisplay()
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
    display = PassthroughDisplay()
    parser = Parser(display.terminal.board)
    parser.feed("\x1b[?1000h")  # child turns on mouse tracking
    # the modes device emits MouseModeChanged -> on_mouse_mode -> host enable printed
    assert "\033[?1000h\033[?1006h" in capsys.readouterr().out
    assert display.host_mouse_mode == "basic"


def test_on_bell_and_on_title(capsys):
    display = PassthroughDisplay()
    display.on_bell()
    assert "\a" in capsys.readouterr().out
    display.on_title("my title", "my title")
    assert "\033]2;my title\007" in capsys.readouterr().out


def test_handle_sgr_mouse_sequence_reinjects(monkeypatch):
    display = PassthroughDisplay()
    calls = []
    monkeypatch.setattr(display.terminal, "input_mouse", lambda *a, **k: calls.append((a, k)))

    assert display.handle_sgr_mouse_sequence("\033[<0;10;5M") is True  # left press at (10,5)
    assert calls == [((10, 5, 0, "press", set()), {})]

    calls.clear()
    assert display.handle_sgr_mouse_sequence("\033[<16;3;4m") is True  # ctrl release
    (x, y, button, event, mods), _ = calls[0]
    assert (x, y, button, event) == (3, 4, 0, "release") and mods == {"ctrl"}

    assert display.handle_sgr_mouse_sequence("garbage") is False  # not a mouse report


def test_shell_detection_returns_something():
    display = PassthroughDisplay()
    assert isinstance(display.get_default_shell(), str)
