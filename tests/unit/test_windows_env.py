"""Test Windows PTY environment string formatting."""

import pytest
from unittest.mock import Mock, patch
from bittty.pty.windows import WindowsPTY


@pytest.mark.windows
def test_env_dict_to_string_conversion():
    """Test that env dict is converted to correct null-separated string format."""

    # Mock winpty to avoid actual PTY creation
    mock_winpty = Mock()
    mock_pty = Mock()
    mock_winpty.PTY.return_value = mock_pty

    with patch("bittty.pty.windows.winpty", mock_winpty):
        pty = WindowsPTY(24, 80)

        # Test with env dict
        test_env = {"PATH": "/bin", "USER": "test", "HOME": "/home/test"}

        # Mock the spawn method to capture the env string
        spawn_calls = []

        def capture_spawn(command, env):
            spawn_calls.append((command, env))

        mock_pty.spawn = capture_spawn

        pty.spawn_process("cmd.exe", env=test_env)

        # Check the call was made
        assert len(spawn_calls) == 1
        command, env_string = spawn_calls[0]

        assert command == "cmd.exe"

        # Parse the env string back to verify format
        env_parts = env_string.rstrip("\0").split("\0")
        reconstructed_env = {}
        for part in env_parts:
            key, value = part.split("=", 1)
            reconstructed_env[key] = value

        assert reconstructed_env == test_env


@pytest.mark.windows
def test_empty_env_string():
    """Test that empty/None env results in empty string."""

    mock_winpty = Mock()
    mock_pty = Mock()
    mock_winpty.PTY.return_value = mock_pty

    with patch("bittty.pty.windows.winpty", mock_winpty):
        pty = WindowsPTY(24, 80)

        spawn_calls = []

        def capture_spawn(command, env):
            spawn_calls.append((command, env))

        mock_pty.spawn = capture_spawn

        # Test with None env
        pty.spawn_process("cmd.exe", env=None)

        assert len(spawn_calls) == 1
        command, env_string = spawn_calls[0]
        assert command == "cmd.exe"
        assert env_string == ""


@pytest.mark.windows
def test_env_with_special_chars():
    """Test env vars with special characters are handled correctly."""

    mock_winpty = Mock()
    mock_pty = Mock()
    mock_winpty.PTY.return_value = mock_pty

    with patch("bittty.pty.windows.winpty", mock_winpty):
        pty = WindowsPTY(24, 80)

        spawn_calls = []

        def capture_spawn(command, env):
            spawn_calls.append((command, env))

        mock_pty.spawn = capture_spawn

        # Test with special chars
        test_env = {"PATH": "C:\\Program Files;C:\\Windows", "TEMP": "C:\\Temp\\with spaces"}

        pty.spawn_process("cmd.exe", env=test_env)

        command, env_string = spawn_calls[0]

        # Verify the string contains the expected format
        assert "PATH=C:\\Program Files;C:\\Windows" in env_string
        assert "TEMP=C:\\Temp\\with spaces" in env_string
        assert env_string.endswith("\0")
