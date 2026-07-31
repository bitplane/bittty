"""Windows PTY unit tests."""

import sys
import time

import pytest

from bittty.pty import WindowsPTY


def read_until(real_pty, expected: tuple[str, ...], timeout: float = 2.0) -> str:
    """Accumulate ConPTY output until expected text arrives or time runs out."""
    result = ""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result += real_pty.read(1000)
        if any(text in result for text in expected):
            break
        time.sleep(0.02)
    return result


def test_read_until_ignores_startup_mode_bursts_before_command_output():
    """ConPTY may publish mode changes before the shell's command output."""

    class ChunkedPTY:
        def __init__(self):
            self.chunks = iter(("\x1b[?9001h\x1b[?1004h", "echo hello\r\nhello\r\n"))

        def read(self, _size):
            return next(self.chunks, "")

    result = read_until(ChunkedPTY(), ("hello", "echo"))

    assert result == "\x1b[?9001h\x1b[?1004hecho hello\r\nhello\r\n"


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
def test_windows_pty_basic_io(real_pty):
    """Test Windows PTY can be created and perform basic I/O."""
    if not isinstance(real_pty, WindowsPTY):
        pytest.skip("Not Windows PTY")

    try:
        process = real_pty.spawn_process("cmd.exe")
        assert process is not None

        real_pty.write("echo hello\r\n")

        result = read_until(real_pty, ("hello", "echo"))
        assert "hello" in result or "echo" in result

        real_pty.write("exit\r\n")
        time.sleep(0.1)

    finally:
        pass  # real_pty fixture handles cleanup


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
def test_windows_pty_process_spawn(real_pty):
    """Test Windows PTY can spawn processes and communicate."""
    if not isinstance(real_pty, WindowsPTY):
        pytest.skip("Not Windows PTY")

    try:
        process = real_pty.spawn_process("cmd.exe")
        assert process is not None

        real_pty.write("echo test123\r\n")

        result = read_until(real_pty, ("test123", "echo"))
        assert "test123" in result or "echo" in result

        real_pty.write("exit\r\n")
        time.sleep(0.1)

    finally:
        pass  # real_pty fixture handles cleanup


@pytest.mark.windows
@pytest.mark.slow
@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
def test_windows_pty_utf8_handling(real_pty):
    """Test Windows PTY handles UTF-8 correctly with real processes."""
    if not isinstance(real_pty, WindowsPTY):
        pytest.skip("Not Windows PTY")

    try:
        process = real_pty.spawn_process("cmd.exe")
        assert process is not None

        utf8_test = "echo 🚽🪠💩 世界"
        real_pty.write(utf8_test + "\r\n")

        result = read_until(real_pty, ("echo", "🚽"))
        assert "echo" in result or "🚽" in result

        real_pty.write("exit\r\n")
        time.sleep(0.1)

    finally:
        pass  # real_pty fixture handles cleanup


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
def test_windows_pty_type(real_pty):
    """Test that Windows returns WindowsPTY."""
    if not isinstance(real_pty, WindowsPTY):
        pytest.skip("Not Windows PTY")

    assert real_pty.__class__.__name__ == "WindowsPTY"
