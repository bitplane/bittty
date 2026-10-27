"""Unix PTY unit tests."""

import asyncio
import os
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

        result = real_pty.read_bytes(1000).decode()
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

        result = real_pty.read_bytes(1000).decode()
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

        result = real_pty.read_bytes(1000).decode()
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


@pytest.mark.unix
@pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
@pytest.mark.asyncio
async def test_cancelled_read_does_not_consume_later_output(real_pty):
    loop = asyncio.get_running_loop()
    errors = []
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda loop, context: errors.append(context))
    try:
        reader = asyncio.create_task(real_pty.read_bytes_async())
        await asyncio.sleep(0)
        reader.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reader
        os.write(real_pty.slave_fd, b"after cancellation")
        await asyncio.sleep(0.02)
        assert errors == []
        assert await asyncio.wait_for(real_pty.read_bytes_async(), 1) == b"after cancellation"
    finally:
        loop.set_exception_handler(previous_handler)


@pytest.mark.unix
@pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
@pytest.mark.asyncio
async def test_cancelling_closed_pty_read_preserves_reused_descriptor_reader(real_pty):
    old_reader = asyncio.create_task(real_pty.read_bytes_async())
    await asyncio.sleep(0)
    old_fd = real_pty.master_fd
    real_pty.close()
    replacement = UnixPTY()
    try:
        assert replacement.master_fd == old_fd
        new_reader = asyncio.create_task(replacement.read_bytes_async())
        await asyncio.sleep(0)
        old_reader.cancel()
        with pytest.raises(asyncio.CancelledError):
            await old_reader
        os.write(replacement.slave_fd, b"new cable")
        assert await asyncio.wait_for(new_reader, 1) == b"new cable"
    finally:
        old_reader.cancel()
        replacement.close()
