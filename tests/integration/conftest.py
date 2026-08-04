"""Integration test fixtures."""

import os
import subprocess
import sys
import tempfile

import pytest


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


def _run_demo(input_commands, timeout=10.0):
    """Internal function to run demo and return output.

    The deadline is a hang detector, not a performance gate: a healthy run
    takes ~0.3s, so it only fires when the demo genuinely fails to exit.
    SHELL is pinned to /bin/sh so the test exercises bittty rather than the
    developer's login shell and rc files — hermetic, and faster.
    """
    demo_path = os.path.join(os.path.dirname(__file__), "..", "..", "demo", "terminal.py")
    env = {**os.environ, "SHELL": "/bin/sh", "ENV": ""}

    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stdout:
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stderr:
            process = subprocess.Popen(
                [sys.executable, demo_path],
                stdin=subprocess.PIPE,
                stdout=stdout,
                stderr=stderr,
                text=True,
                cwd=os.path.dirname(demo_path),
                env=env,
            )
            try:
                process.stdin.write(input_commands)
                process.stdin.flush()
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired as error:
                process.terminate()
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                stdout.seek(0)
                stderr.seek(0)
                raise DemoTimeoutError(
                    f"Demo timed out after {timeout}s",
                    stdout=stdout.read(),
                    stderr=stderr.read(),
                ) from error
            finally:
                process.stdin.close()

            stdout.seek(0)
            stderr.seek(0)
            output = stdout.read()
            error_output = stderr.read()
            if returncode != 0:
                pytest.fail(f"Demo exited with status {returncode}\n\nstdout:\n{output}\n\nstderr:\n{error_output}")
            return output


@pytest.fixture
def assert_demo_output():
    """Assert that demo output contains expected text, with nice screen dump on failure."""

    def _assert(commands, expected, timeout=10.0):
        """Run demo with commands and assert output contains expected text.

        Args:
            commands: Commands to send to demo (include \r\n for newlines)
            expected: String or list of strings that should appear in output
            timeout: Hang-detection deadline in seconds (default 10.0)
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
