"""Tests for StdioPTY implementation."""

import asyncio
import io
import sys
import pytest

from bittty.pty import StdioPTY


@pytest.mark.asyncio
async def test_stdio_pty_basic():
    """Test basic StdioPTY functionality with Python print command."""
    # Create string buffers for stdin/stdout
    stdin_buffer = io.StringIO()
    stdout_buffer = io.StringIO()

    # Create StdioPTY instance
    pty = StdioPTY(stdin_buffer, stdout_buffer, rows=24, cols=80)

    # Spawn Python process to print hello world
    command = [sys.executable, "-c", "print('Hello, World!')"]
    pty.spawn_process(command)

    # Set non-blocking mode
    pty.set_nonblocking()

    # Read output in a loop until we get data or timeout
    output = ""
    timeout = 5.0  # 5 second timeout
    start_time = asyncio.get_event_loop().time()

    while asyncio.get_event_loop().time() - start_time < timeout:
        data = await pty.read_async()
        if data:
            output += data
            # Check if we got the expected output
            if "Hello, World!" in output:
                break
        else:
            await asyncio.sleep(0.01)

    # Clean up
    pty.close()

    # Verify output was written to stdout
    stdout_content = stdout_buffer.getvalue()
    assert "Hello, World!" in stdout_content

    # Also verify it was returned from read
    assert "Hello, World!" in output


@pytest.mark.asyncio
async def test_stdio_pty_stdin_forwarding():
    """Test that stdin input is forwarded to the process."""

    # Create string buffer for stdout and a custom stdin
    class MockStdin:
        def __init__(self, data):
            self.data = data.encode("utf-8")
            self.position = 0

        def fileno(self):
            # Return a fake file descriptor
            return -1

        def read(self, size):
            if self.position >= len(self.data):
                return b""
            result = self.data[self.position : self.position + size]
            self.position += len(result)
            return result

    stdin = MockStdin("test input\n")
    stdout_buffer = io.StringIO()

    # Create StdioPTY instance
    pty = StdioPTY(stdin, stdout_buffer, rows=24, cols=80)

    # Spawn a simple echo process with Python
    command = [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read()); sys.stdout.flush()"]
    pty.spawn_process(command)

    # Set non-blocking mode
    pty.set_nonblocking()

    # Give it some time to process
    await asyncio.sleep(0.5)

    # Clean up
    pty.close()

    # For this test, we're mainly checking that it doesn't crash
    # Real stdin forwarding would require actual file descriptors


def test_stdio_pty_resize():
    """Test that resize works properly."""
    stdin_buffer = io.StringIO()
    stdout_buffer = io.StringIO()

    pty = StdioPTY(stdin_buffer, stdout_buffer, rows=24, cols=80)

    # Initial size
    assert pty.rows == 24
    assert pty.cols == 80

    # Resize
    pty.resize(30, 100)
    assert pty.rows == 30
    assert pty.cols == 100

    pty.close()


@pytest.mark.asyncio
async def test_stdio_pty_write():
    """Test writing data to the PTY."""
    stdin_buffer = io.StringIO()
    stdout_buffer = io.StringIO()

    pty = StdioPTY(stdin_buffer, stdout_buffer)

    # Create background PTY first by spawning a process
    command = [sys.executable, "-c", "import time; time.sleep(0.1)"]
    pty.spawn_process(command)

    # Write some data
    bytes_written = pty.write("test data")
    assert bytes_written > 0

    # Give it a moment to clean up
    await asyncio.sleep(0.01)

    pty.close()


def test_stdio_pty_closed_state():
    """Test operations on closed PTY."""
    stdin_buffer = io.StringIO()
    stdout_buffer = io.StringIO()

    pty = StdioPTY(stdin_buffer, stdout_buffer)
    pty.close()

    # Operations should handle closed state gracefully
    assert pty.closed
    assert pty.read() == ""
    assert pty.write("test") == 0

    # Spawning process on closed PTY should raise
    with pytest.raises(OSError):
        pty.spawn_process("echo test")
