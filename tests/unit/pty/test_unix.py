"""Unix PTY unit tests."""

import sys
import pytest
from bittty.pty import UnixPTY


@pytest.mark.unix
@pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
def test_unix_pty_basic_io(real_pty):
    """Test Unix PTY can be created and perform basic I/O."""
    if not isinstance(real_pty, UnixPTY):
        pytest.skip("Not Unix PTY")

    try:
        process = real_pty.spawn_process("/bin/bash")
        assert process is not None
        assert process.poll() is None

        real_pty.write("echo hello\n")

        import time

        time.sleep(0.1)

        result = real_pty.read(1000)
        assert "hello" in result or "echo" in result

        real_pty.write("exit\n")
        time.sleep(0.1)

    finally:
        pass  # real_pty fixture handles cleanup


@pytest.mark.unix
@pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
def test_unix_pty_process_spawn(real_pty):
    """Test Unix PTY can spawn processes and communicate."""
    if not isinstance(real_pty, UnixPTY):
        pytest.skip("Not Unix PTY")

    try:
        process = real_pty.spawn_process("/bin/bash")
        assert process is not None
        assert process.poll() is None

        real_pty.write("echo test123\n")

        import time

        time.sleep(0.1)

        result = real_pty.read(1000)
        assert "test123" in result or "echo" in result

        real_pty.write("exit\n")
        time.sleep(0.1)

    finally:
        pass  # real_pty fixture handles cleanup


@pytest.mark.unix
@pytest.mark.slow
@pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
def test_unix_pty_utf8_handling(real_pty):
    """Test Unix PTY handles UTF-8 correctly with real processes."""
    if not isinstance(real_pty, UnixPTY):
        pytest.skip("Not Unix PTY")

    try:
        process = real_pty.spawn_process("/bin/bash")
        assert process is not None

        utf8_test = "echo '🚽🪠💩 世界'"
        real_pty.write(utf8_test + "\n")

        import time

        time.sleep(0.2)

        result = real_pty.read(1000)
        assert "🚽" in result or "echo" in result
        assert "�" not in result

        real_pty.write("exit\n")
        time.sleep(0.1)

    finally:
        pass  # real_pty fixture handles cleanup


@pytest.mark.unix
@pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
def test_unix_pty_type(real_pty):
    """Test that Unix returns UnixPTY."""
    if not isinstance(real_pty, UnixPTY):
        pytest.skip("Not Unix PTY")

    assert real_pty.__class__.__name__ == "UnixPTY"
