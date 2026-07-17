from bittty.operations import Operation
from bittty import Board


def test_title_device_owns_title_state():
    terminal = Board(width=20, height=5)
    title = terminal.board.title

    title.set_title("Window")
    title.set_icon_title("Icon")

    assert title.title == "Window"
    assert title.icon_title == "Icon"
    assert terminal.board.title.title == "Window"
    assert terminal.board.title.icon_title == "Icon"


def test_title_device_handles_title_operations():
    terminal = Board(width=20, height=5)
    title = terminal.board.title

    title.handle_operation(Operation("SET_ICON_AND_WINDOW_TITLE", ("Both",), "\x1b]0;Both\x07"))
    assert (title.title, title.icon_title) == ("Both", "Both")

    title.handle_operation(Operation("SET_WINDOW_TITLE", ("Window",), "\x1b]2;Window\x07"))
    assert (title.title, title.icon_title) == ("Window", "Both")

    title.handle_operation(Operation("SET_ICON_TITLE", ("Icon",), "\x1b]1;Icon\x07"))
    assert (title.title, title.icon_title) == ("Window", "Icon")
