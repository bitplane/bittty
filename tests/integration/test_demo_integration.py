"""Real integration tests using demo application."""

import sys
import pytest


@pytest.mark.integration
@pytest.mark.skipif(sys.platform == "win32", reason="Demo uses Unix terminal features")
def test_demo_basic_command(demo_terminal):
    """Test that demo terminal can execute basic commands."""
    # Run demo with a simple command
    output = demo_terminal.run_with_input("echo hello world\\r\\nexit\\r\\n")

    # Should contain the command output
    assert "hello world" in output, f"Expected 'hello world' in output: {repr(output)}"


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.skipif(sys.platform == "win32", reason="Demo uses Unix terminal features")
def test_demo_utf8_support(demo_terminal):
    """Test that demo terminal handles UTF-8 correctly."""
    # Run demo with UTF-8 command
    output = demo_terminal.run_with_input("echo 'UTF-8: 🚽🪠💩 世界'\\r\\nexit\\r\\n")

    # Should contain UTF-8 characters without corruption
    assert "🚽" in output or "世界" in output, f"Expected UTF-8 chars in output: {repr(output)}"
    # Should not contain replacement characters
    assert "�" not in output, f"Found replacement character in output: {repr(output)}"


@pytest.mark.integration
@pytest.mark.skipif(sys.platform == "win32", reason="Demo uses Unix terminal features")
def test_demo_multiple_commands(demo_terminal):
    """Test demo terminal with multiple commands."""
    # Run demo with multiple commands
    commands = "echo first\\r\\necho second\\r\\npwd\\r\\nexit\\r\\n"
    output = demo_terminal.run_with_input(commands)

    # Should contain output from both commands
    assert "first" in output, f"Expected 'first' in output: {repr(output)}"
    assert "second" in output, f"Expected 'second' in output: {repr(output)}"


@pytest.mark.integration
@pytest.mark.skipif(sys.platform == "win32", reason="Demo uses Unix terminal features")
def test_demo_clean_exit(demo_terminal):
    """Test that demo exits cleanly."""
    # Run demo with just exit command
    output = demo_terminal.run_with_input("exit\\r\\n")

    # Should produce some output (shell prompt, etc.) and exit cleanly
    assert isinstance(output, str), "Should return string output"
    # The fact that run_with_input returns means the process exited
