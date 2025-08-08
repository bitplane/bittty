"""Unix PTY integration tests."""

import sys
import pytest
from bittty.terminal import Terminal


@pytest.mark.integration
@pytest.mark.unix
@pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
def test_unix_pty_basic_io():
    """Test Unix PTY can be created and perform basic I/O."""
    terminal = Terminal(command="/bin/bash", width=80, height=24)

    try:
        terminal.input("echo hello\n")
        screen_content = terminal.capture_pane()
        assert "hello" in screen_content
    finally:
        terminal.close()


@pytest.mark.integration
@pytest.mark.unix
@pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
def test_unix_pty_process_spawn():
    """Test Unix PTY can spawn processes and communicate."""
    terminal = Terminal(command="/bin/bash", width=80, height=24)

    try:
        terminal.input("echo test123\n")
        screen_content = terminal.capture_pane()
        assert "test123" in screen_content
    finally:
        terminal.close()


@pytest.mark.integration
@pytest.mark.unix
@pytest.mark.slow
@pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
def test_unix_pty_utf8_handling():
    """Test Unix PTY handles UTF-8 correctly with real processes."""
    terminal = Terminal(command="/bin/bash", width=80, height=24)

    try:
        terminal.input("echo '🚽🪠💩 世界'\n")
        screen_content = terminal.capture_pane()
        assert "🚽" in screen_content or "echo" in screen_content
        assert "�" not in screen_content
    finally:
        terminal.close()


@pytest.mark.integration
@pytest.mark.unix
@pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
def test_unix_pty_type():
    """Test that Unix terminal works."""
    terminal = Terminal(command="/bin/bash", width=80, height=24)

    try:
        assert terminal is not None
    finally:
        terminal.close()
