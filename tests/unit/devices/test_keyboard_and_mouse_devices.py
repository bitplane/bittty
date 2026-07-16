from bittty import constants
from bittty.terminal import Terminal


class RecordingPTY:
    def __init__(self):
        self.data = []

    def write(self, data):
        self.data.append(data)

    def flush(self):
        pass


def terminal_with_pty():
    terminal = Terminal(width=20, height=5)
    terminal.pty = RecordingPTY()
    return terminal


def test_keyboard_device_encodes_keys_and_application_cursor_mode():
    terminal = terminal_with_pty()

    terminal.board.keyboard.input_key("up")
    terminal.board.modes.cursor_application_mode = True
    terminal.board.keyboard.input_key("down")
    terminal.board.keyboard.input_key("a", constants.KEY_MOD_CTRL)

    assert terminal.pty.data == ["\x1b[A", "\x1bOB", "\x01"]
    assert terminal.board.host.transport is terminal.pty


def test_keyboard_device_encodes_function_and_numpad_keys():
    terminal = terminal_with_pty()

    terminal.board.keyboard.input_fkey(1)
    terminal.board.keyboard.input_fkey(5, constants.KEY_MOD_CTRL)
    terminal.board.keyboard.input_numpad_key("5")
    terminal.board.modes.numeric_keypad = False
    terminal.board.keyboard.input_numpad_key("Enter")

    assert terminal.pty.data == ["\x1bOP", "\x1b[15;5~", "5", "\x1bOM"]


def test_keyboard_device_backarrow_mode():
    terminal = terminal_with_pty()

    terminal.board.keyboard.input_key(constants.BS)
    terminal.board.modes.backarrow_key_sends_bs = True
    terminal.board.keyboard.input_key(constants.BS)

    assert terminal.pty.data == [constants.DEL, constants.BS]


def test_mouse_device_caches_position_and_gates_tracking():
    terminal = terminal_with_pty()
    mouse = terminal.board.mouse

    mouse.input_mouse(10, 5, 0, "press", set())
    assert (mouse.x, mouse.y) == (10, 5)
    assert terminal.pty.data == []

    terminal.board.modes.mouse_tracking = True
    terminal.board.modes.mouse_sgr_mode = True
    mouse.input_mouse(10, 5, 0, "press", {"shift"})

    assert terminal.pty.data == ["\x1b[<4;10;5M"]


def test_mouse_device_move_requires_any_tracking():
    terminal = terminal_with_pty()
    terminal.board.modes.mouse_tracking = True
    terminal.board.modes.mouse_sgr_mode = True

    terminal.board.mouse.input_mouse(1, 2, 0, "move", set())
    assert terminal.pty.data == []

    terminal.board.modes.mouse_any_tracking = True
    terminal.board.mouse.input_mouse(1, 2, 0, "move", set())
    assert terminal.pty.data == ["\x1b[<35;1;2M"]
