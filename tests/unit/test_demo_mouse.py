import importlib.util
from pathlib import Path


def load_demo_module():
    demo_path = Path(__file__).parents[2] / "demo" / "terminal.py"
    spec = importlib.util.spec_from_file_location("bittty_demo_terminal", demo_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeTerminal:
    def __init__(self):
        self.mouse_events = []
        self.keyboard_input = []

    def input_mouse(self, x, y, button, event_type, modifiers):
        self.mouse_events.append((x, y, button, event_type, modifiers))

    def input(self, data):
        self.keyboard_input.append(data)


def make_frontend():
    module = load_demo_module()
    frontend = module.StdoutFrontend.__new__(module.StdoutFrontend)
    frontend.terminal = FakeTerminal()
    frontend.input_sequence_buffer = ""
    return frontend


def test_demo_forwards_sgr_mouse_press():
    frontend = make_frontend()

    for char in "\033[<20;15;8M":
        frontend.handle_input(char)

    assert frontend.terminal.mouse_events == [(15, 8, 0, "press", {"shift", "ctrl"})]
    assert frontend.terminal.keyboard_input == []


def test_demo_forwards_non_mouse_escape_input():
    frontend = make_frontend()

    for char in "\033[A":
        frontend.handle_input(char)

    assert frontend.terminal.mouse_events == []
    assert "".join(frontend.terminal.keyboard_input) == "\033[A"
