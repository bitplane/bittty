"""Integration test fixtures."""

import subprocess
import pytest


@pytest.fixture
def demo_terminal():
    """Run demo/terminal.py with pre-written input and capture output."""
    import os
    import tempfile

    # Path to demo script relative to project root
    demo_path = os.path.join(os.path.dirname(__file__), "..", "..", "demo", "terminal.py")

    # Create a temporary file for output
    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as output_file:
        output_path = output_file.name

    class DemoRunner:
        def __init__(self, demo_path, output_path):
            self.demo_path = demo_path
            self.output_path = output_path

        def run_with_input(self, input_commands):
            """Run demo with given input commands and return output."""
            process = subprocess.Popen(
                f"printf '{input_commands}' | python3 {self.demo_path} > {self.output_path}",
                shell=True,
                cwd=os.path.dirname(self.demo_path),
            )
            process.wait()

            with open(self.output_path, "r") as f:
                return f.read()

    runner = DemoRunner(demo_path, output_path)

    yield runner

    # Cleanup
    os.unlink(output_path)
