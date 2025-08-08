"""Integration test fixtures."""

import subprocess
import pytest
import os


class DemoTimeoutError(Exception):
    """Custom exception for demo timeouts with screen debugging."""

    def __init__(self, message, stdout="", stderr="", height=24):
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr

        # Extract last `height` rows from stdout for screen debugging
        if stdout:
            lines = stdout.split("\n")
            last_lines = lines[-height:] if len(lines) > height else lines
            screen_content = "\n".join(last_lines)
            enhanced_message = f"{message}\n\nLast {len(last_lines)} rows of screen:\n{screen_content}"
        else:
            enhanced_message = f"{message}\n\nNo stdout captured"

        self.args = (enhanced_message,)


def _run_demo(input_commands, timeout=2.0):
    """Internal function to run demo and return output."""
    demo_path = os.path.join(os.path.dirname(__file__), "..", "..", "demo", "terminal.py")

    try:
        result = subprocess.run(
            ["python3", demo_path],
            input=input_commands,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.path.dirname(demo_path),
        )
        return result.stdout
    except subprocess.TimeoutExpired as e:
        # Convert to our custom exception with screen debugging
        stdout = e.stdout.decode("utf-8") if e.stdout else ""
        stderr = e.stderr.decode("utf-8") if e.stderr else ""
        raise DemoTimeoutError(f"Demo timed out after {timeout}s", stdout=stdout, stderr=stderr) from e


@pytest.fixture
def assert_demo_output():
    """Assert that demo output contains expected text, with nice screen dump on failure."""

    def _assert(commands, expected, timeout=2.0):
        """Run demo with commands and assert output contains expected text.

        Args:
            commands: Commands to send to demo (include \r\n for newlines)
            expected: String or list of strings that should appear in output
            timeout: Timeout in seconds (default 2.0)
        """
        # Ensure commands end with exit
        if not commands.strip().endswith("exit"):
            commands = commands.rstrip() + "\r\nexit\r\n"

        output = _run_demo(commands, timeout)

        # Handle both string and list expectations
        if isinstance(expected, str):
            expected = [expected]

        # Check each expected string
        for exp in expected:
            if exp not in output:
                # Pretty screen dump on failure
                lines = output.split("\n")
                screen_display = "\n".join(lines[-24:] if len(lines) > 24 else lines)

                pytest.fail(
                    f"Expected '{exp}' not found in output\n\n"
                    f"=== Last {min(24, len(lines))} rows of screen ===\n"
                    f"{screen_display}\n"
                    f"=== End of screen ===\n\n"
                    f"Full output ({len(output)} chars):\n{repr(output)}"
                )

        return output  # Return for additional checks if needed

    return _assert
