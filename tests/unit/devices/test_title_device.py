from bittty.operations import Operation
from bittty.terminal import Terminal


def test_title_device_owns_title_state():
    terminal = Terminal(width=20, height=5)
    title = terminal.title_device

    title.set_title("Window")
    title.set_icon_title("Icon")

    assert title.title == "Window"
    assert title.icon_title == "Icon"
    assert terminal.title == "Window"
    assert terminal.icon_title == "Icon"


def test_title_device_handles_title_operations():
    terminal = Terminal(width=20, height=5)
    title = terminal.title_device

    title.handle_operation(Operation("title", "SET_ICON_AND_WINDOW_TITLE", ("Both",), "\x1b]0;Both\x07"))
    assert (title.title, title.icon_title) == ("Both", "Both")

    title.handle_operation(Operation("title", "SET_WINDOW_TITLE", ("Window",), "\x1b]2;Window\x07"))
    assert (title.title, title.icon_title) == ("Window", "Both")

    title.handle_operation(Operation("title", "SET_ICON_TITLE", ("Icon",), "\x1b]1;Icon\x07"))
    assert (title.title, title.icon_title) == ("Window", "Icon")
