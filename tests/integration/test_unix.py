"""Unix PTY integration tests."""

import pytest
from bittty.pty import UnixPTY


@pytest.mark.integration
@pytest.mark.unix
def test_unix_pty_basic_io():
    """Test Unix PTY can be created and perform basic I/O."""
    pty = UnixPTY(24, 80)

    try:
        pty.write("echo hello\n")

        import time

        time.sleep(0.1)

        result = pty.read(1000)
        assert "hello" in result or "echo" in result

    finally:
        pty.close()


@pytest.mark.integration
@pytest.mark.unix
def test_unix_pty_process_spawn():
    """Test Unix PTY can spawn processes and communicate."""
    pty = UnixPTY(24, 80)

    try:
        process = pty.spawn_process("/bin/bash")
        assert process is not None
        assert process.poll() is None

        pty.write("echo test123\n")

        import time

        time.sleep(0.1)
        result = pty.read(1000)

        assert "test123" in result or "echo" in result

        pty.write("exit\n")
        time.sleep(0.1)

    finally:
        pty.close()


@pytest.mark.integration
@pytest.mark.unix
@pytest.mark.slow
def test_unix_pty_utf8_handling():
    """Test Unix PTY handles UTF-8 correctly with real processes."""
    pty = UnixPTY(24, 80)

    try:
        pty.spawn_process("/bin/bash")

        utf8_test = "echo '🚽🪠💩 世界'"
        pty.write(utf8_test + "\n")

        import time

        time.sleep(0.2)

        result = pty.read(1000)

        assert "🚽" in result or "echo" in result
        assert "�" not in result

        pty.write("exit\n")
        time.sleep(0.1)

    finally:
        pty.close()


@pytest.mark.integration
@pytest.mark.unix
def test_unix_pty_type():
    """Test that Unix returns UnixPTY."""
    pty = UnixPTY(24, 80)

    try:
        assert pty.__class__.__name__ == "UnixPTY"
    finally:
        pty.close()
