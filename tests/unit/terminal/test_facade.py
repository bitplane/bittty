from bittty import constants
from bittty.style import parse_sgr_sequence
from bittty.terminal import Terminal


class RecordingPTY:
    def __init__(self):
        self.data = []

    def write(self, data):
        self.data.append(data)

    def flush(self):
        pass


def test_terminal_cursor_facade_proxies_cursor_device():
    terminal = Terminal(width=10, height=5)

    terminal.cursor_x = 3
    terminal.cursor_y = 2
    terminal.current_ansi_code = "\x1b[31m"
    terminal.save_cursor()

    terminal.set_cursor(20, 20)
    terminal.current_ansi_code = "\x1b[32m"
    terminal.restore_cursor()

    assert (terminal.cursor.x, terminal.cursor.y) == (3, 2)
    assert (terminal.cursor_x, terminal.cursor_y) == (3, 2)
    assert terminal.current_ansi_code == "\x1b[31m"


def test_terminal_screen_facade_proxies_screen_device():
    terminal = Terminal(width=8, height=3)

    assert terminal.current_buffer is terminal.screen.current_buffer
    terminal.write_text("abc")
    assert terminal.screen.current_buffer.get_line_text(0).startswith("abc")

    terminal.clear_screen(constants.ERASE_ALL)
    assert terminal.screen.current_buffer.get_line_text(0).strip() == ""

    terminal.current_buffer.set(0, 0, "top")
    terminal.scroll_up(1)
    assert terminal.screen.current_buffer.get_line_text(0).strip() == ""


def test_terminal_resize_and_alt_screen_facade():
    terminal = Terminal(width=10, height=5)
    terminal.cursor_x = 9
    terminal.cursor_y = 4

    terminal.resize(5, 2)
    assert (terminal.width, terminal.height) == (5, 2)
    assert (terminal.cursor_x, terminal.cursor_y) == (4, 1)
    assert terminal.scroll_bottom == 1

    terminal.current_buffer.set(0, 0, "main")
    terminal.alternate_screen_on()
    assert terminal.in_alt_screen is True
    assert terminal.current_buffer is terminal.alt_buffer
    terminal.alternate_screen_off()
    assert terminal.current_buffer.get_line_text(0).startswith("main")


def test_terminal_style_and_charset_facades():
    terminal = Terminal(width=10, height=3)

    terminal.current_ansi_code = "\x1b[31m"
    assert terminal.style.current_ansi_code == "\x1b[31m"

    terminal.set_g0_charset("0")
    assert terminal.g0_charset == "0"
    assert terminal._translate_charset("q") == "─"

    terminal.set_g1_charset("0")
    terminal.shift_out()
    assert terminal.current_charset == 1
    terminal.shift_in()
    assert terminal.current_charset == 0

    terminal.set_g2_charset("0")
    terminal.single_shift_2()
    assert terminal.single_shift == 2
    assert terminal._translate_charset("q") == "─"
    assert terminal.single_shift is None


def test_terminal_mode_facade_proxies_mode_device():
    terminal = Terminal(width=10, height=3)

    terminal.auto_wrap = False
    terminal.insert_mode = True
    terminal.mouse_sgr_mode = True
    terminal.bracketed_paste = True

    assert terminal.modes.auto_wrap is False
    assert terminal.modes.insert_mode is True
    assert terminal.modes.mouse_sgr_mode is True
    assert terminal.modes.bracketed_paste is True

    terminal.set_mode(constants.DECAWM_AUTOWRAP, True, private=True)
    terminal.clear_mode(constants.IRM_INSERT_REPLACE)
    assert terminal.auto_wrap is True
    assert terminal.insert_mode is False


def test_terminal_title_and_mouse_facades():
    terminal = Terminal(width=20, height=5)

    terminal.set_title("Window")
    terminal.set_icon_title("Icon")
    assert terminal.title_device.title == "Window"
    assert terminal.title_device.icon_title == "Icon"
    assert terminal.title == "Window"
    assert terminal.icon_title == "Icon"

    terminal.show_mouse = True
    terminal.mouse_x = 5
    terminal.mouse_y = 3
    assert terminal.mouse.show is True
    assert (terminal.mouse.x, terminal.mouse.y) == (5, 3)
    assert terminal.capture_pane().split("\n")[2][4] == "↖"


def test_terminal_keyboard_and_mouse_input_facades():
    terminal = Terminal(width=20, height=5)
    terminal.pty = RecordingPTY()

    terminal.input_key("up")
    terminal.cursor_application_mode = True
    terminal.input_key("down")
    terminal.input_fkey(5, constants.KEY_MOD_CTRL)
    terminal.input_numpad_key("Enter")

    terminal.mouse_tracking = True
    terminal.mouse_sgr_mode = True
    terminal.input_mouse(2, 3, 0, "press", {"shift"})

    assert terminal.pty.data == [
        "\x1b[A",
        "\x1bOB",
        "\x1b[15;5~",
        "\r",
        "\x1b[<4;2;3M",
    ]


def test_terminal_write_and_edit_facades_preserve_styles():
    terminal = Terminal(width=10, height=3)
    terminal.current_ansi_code = "\x1b[31m"
    terminal.write_text("abc")
    assert terminal.current_buffer.get_cell(0, 0) == (parse_sgr_sequence("\x1b[31m"), "a")

    terminal.cursor_x = 1
    terminal.insert_characters(2, "\x1b[32m")
    assert terminal.current_buffer.get_cell(1, 0) == (parse_sgr_sequence("\x1b[32m"), " ")

    terminal.delete_characters(2)
    terminal.set_scroll_region(0, 2)
    terminal.alignment_test()
    assert terminal.current_buffer.get_line_text(0) == "E" * terminal.width
