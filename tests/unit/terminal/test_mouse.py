from bittty.terminal import Terminal


def test_show_mouse_cursor():
    """Test that the mouse cursor is rendered when show_mouse is True."""
    # Create a terminal
    terminal = Terminal(width=20, height=10)

    # Enable the mouse cursor
    terminal.show_mouse = True

    # Set a mouse position
    terminal.mouse_x = 5
    terminal.mouse_y = 3

    # Get the content and check for the cursor
    content = terminal.capture_pane()
    # The mouse cursor is at (5,3), which is index 4 of line 2 (0-indexed)
    # The capture_pane output includes newlines, so we need to split it.
    lines = content.split("\n")
    assert lines[2][4] == "↖"

    # Disable the mouse cursor
    terminal.show_mouse = False

    # Get the content and check that the cursor is gone
    content = terminal.capture_pane()
    lines = content.split("\n")
    assert lines[2][4] != "↖"
