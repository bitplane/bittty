"""The stdio terminal's input demux: SGR mouse interception vs. raw forwarding."""

from bittty.parser import Parser

from bittty.terminals.stdio import HostInputSink, StdioTerminal


class FakeBoard:
    def __init__(self):
        self.display = self  # stands in for both the board and its display port
        self.mouse_events = []
        self.keyboard_input = []

    def input_mouse(self, x, y, button, event_type, modifiers):
        self.mouse_events.append((x, y, button, event_type, modifiers))

    def input(self, data):
        self.keyboard_input.append(data)


def make_frontend():
    # Bypass __init__ (no real board/tty needed to test the input demux).
    frontend = StdioTerminal.__new__(StdioTerminal)
    frontend.board = FakeBoard()
    frontend.input_parser = Parser(HostInputSink(frontend))
    return frontend


def test_demo_forwards_sgr_mouse_press():
    frontend = make_frontend()

    for char in "\033[<20;15;8M":
        frontend.handle_input(char)

    assert frontend.board.mouse_events == [(15, 8, 0, "press", {"shift", "ctrl"})]
    assert frontend.board.keyboard_input == []


def test_demo_forwards_non_mouse_escape_input():
    frontend = make_frontend()

    for char in "\033[A":
        frontend.handle_input(char)

    assert frontend.board.mouse_events == []
    assert "".join(frontend.board.keyboard_input) == "\033[A"
