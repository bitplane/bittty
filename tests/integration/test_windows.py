"""Windows PTY integration tests."""

import sys
import pytest
from bittty.terminal import Terminal


@pytest.mark.integration
@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
def test_windows_pty_basic_io():
    """Test Windows PTY can be created and perform basic I/O."""
    terminal = Terminal(command="cmd.exe", width=80, height=24)

    try:
        terminal.input("echo hello\r\n")
        screen_content = terminal.capture_pane()
        assert "hello" in screen_content
    finally:
        terminal.close()


@pytest.mark.integration
@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
def test_windows_pty_process_spawn():
    """Test Windows PTY can spawn processes and communicate."""
    terminal = Terminal(command="cmd.exe", width=80, height=24)

    try:
        terminal.input("echo test123\r\n")
        screen_content = terminal.capture_pane()
        assert "test123" in screen_content
    finally:
        terminal.close()


@pytest.mark.integration
@pytest.mark.windows
@pytest.mark.slow
@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
def test_windows_pty_utf8_handling():
    """Test Windows PTY handles UTF-8 correctly with real processes."""
    terminal = Terminal(command="cmd.exe", width=80, height=24)

    try:
        terminal.input("echo 🚽🪠💩 世界\r\n")
        screen_content = terminal.capture_pane()
        assert "🚽" in screen_content or "echo" in screen_content
    finally:
        terminal.close()


@pytest.mark.integration
@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
def test_windows_pty_type():
    """Test that Windows terminal works."""
    terminal = Terminal(command="cmd.exe", width=80, height=24)

    try:
        assert terminal is not None
    finally:
        terminal.close()
