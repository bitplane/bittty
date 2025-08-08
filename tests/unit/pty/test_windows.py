"""Windows PTY unit tests."""

import sys
import pytest
from bittty.pty import WindowsPTY


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

        import time

        time.sleep(0.2)

        result = real_pty.read(1000)
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

        import time

        time.sleep(0.2)

        result = real_pty.read(1000)
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

        import time

        time.sleep(0.3)

        result = real_pty.read(1000)
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
