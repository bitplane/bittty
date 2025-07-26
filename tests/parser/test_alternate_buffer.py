import pytest
from unittest.mock import Mock
from bittty.parser import Parser
from bittty.terminal import Terminal
from rich.style import Style
from bittty.constants import (
    DEFAULT_TERMINAL_WIDTH,
    DEFAULT_TERMINAL_HEIGHT,
    ALT_SCREEN_BUFFER,
    ESC,
)


@pytest.fixture
def terminal():
    """Return a mock Screen object with necessary attributes."""
    terminal = Mock(spec=Terminal)
    terminal.current_style = Style()  # Initialize with a real Style object
    terminal.width = DEFAULT_TERMINAL_WIDTH
    terminal.height = DEFAULT_TERMINAL_HEIGHT
    terminal.cursor_x = 0
    terminal.cursor_y = 0
    terminal.scroll_top = 0
    terminal.scroll_bottom = terminal.height - 1
    terminal.auto_wrap = True
    terminal.cursor_visible = True

    def _set_cursor(x, y):
        if x is not None:
            terminal.cursor_x = x
        if y is not None:
            terminal.cursor_y = y

    terminal.set_cursor.side_effect = _set_cursor
    return terminal


def test_alternate_buffer_enable(terminal):
    """Test CSI ? 1049 h (Enable alternate terminal buffer)."""
    parser = Parser(terminal)
    parser.feed(f"{ESC}[?{ALT_SCREEN_BUFFER}h")

    # Should call alternate_screen_on
    terminal.alternate_screen_on.assert_called_once()


def test_alternate_buffer_disable(terminal):
    """Test CSI ? 1049 l (Disable alternate terminal buffer)."""
    parser = Parser(terminal)
    parser.feed("\x1b[?1049l")

    # Should call alternate_screen_off
    terminal.alternate_screen_off.assert_called_once()


def test_alternate_buffer_enable_disable_sequence(terminal):
    """Test enabling then disabling alternate buffer."""
    parser = Parser(terminal)

    # Enable
    parser.feed("\x1b[?1049h")
    terminal.alternate_screen_on.assert_called_once()

    # Disable
    parser.feed("\x1b[?1049l")
    terminal.alternate_screen_off.assert_called_once()


def test_alternate_buffer_with_other_modes(terminal):
    """Test alternate buffer mode combined with other modes."""
    parser = Parser(terminal)

    # Multiple modes at once: cursor visibility + alternate buffer
    parser.feed("\x1b[?25;1049h")

    # Both should be called
    assert terminal.cursor_visible is True
    terminal.alternate_screen_on.assert_called_once()


def test_alternate_buffer_mixed_set_reset(terminal):
    """Test mixed set/reset operations on alternate buffer and other modes."""
    parser = Parser(terminal)

    # Enable cursor + alternate buffer
    parser.feed("\x1b[?25;1049h")
    assert terminal.cursor_visible is True
    terminal.alternate_screen_on.assert_called_once()

    # Disable cursor, keep alternate buffer enabled
    parser.feed("\x1b[?25l")
    assert terminal.cursor_visible is False

    # Disable alternate buffer
    parser.feed("\x1b[?1049l")
    terminal.alternate_screen_off.assert_called_once()
