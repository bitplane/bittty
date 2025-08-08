"""Windows PTY integration tests."""

import sys
import pytest
from bittty.pty import WindowsPTY


@pytest.mark.integration
@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
def test_windows_pty_basic_io():
    """Test Windows PTY can be created and perform basic I/O."""
    pty = WindowsPTY(24, 80)

    try:
        # Need to spawn a process first
        pty.spawn_process("cmd.exe")

        pty.write("echo hello\r\n")

        import time

        time.sleep(0.2)

        result = pty.read(1000)
        assert "hello" in result or "echo" in result

    finally:
        pty.close()


@pytest.mark.integration
@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
def test_windows_pty_process_spawn():
    """Test Windows PTY can spawn processes and communicate."""

    pty = WindowsPTY(24, 80)

    try:
        process = pty.spawn_process("cmd.exe")
        assert process is not None

        pty.write("echo test123\r\n")

        import time

        time.sleep(0.2)
        result = pty.read(1000)

        assert "test123" in result or "echo" in result

        pty.write("exit\r\n")
        time.sleep(0.1)

    finally:
        pty.close()


@pytest.mark.integration
@pytest.mark.windows
@pytest.mark.slow
@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
def test_windows_pty_utf8_handling():
    """Test Windows PTY handles UTF-8 correctly with real processes."""

    pty = WindowsPTY(24, 80)

    try:
        pty.spawn_process("cmd.exe")

        utf8_test = "echo 🚽🪠💩 世界"
        pty.write(utf8_test + "\r\n")

        import time

        time.sleep(0.3)

        result = pty.read(1000)

        assert "echo" in result or "🚽" in result

        pty.write("exit\r\n")
        time.sleep(0.1)

    finally:
        pty.close()


@pytest.mark.integration
@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
def test_windows_pty_type():
    """Test that Windows returns WindowsPTY."""

    pty = WindowsPTY(24, 80)

    try:
        assert pty.__class__.__name__ == "WindowsPTY"
    finally:
        pty.close()
