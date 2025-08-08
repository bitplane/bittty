"""Real integration tests using demo application."""

import sys
import pytest


@pytest.mark.integration
@pytest.mark.skipif(sys.platform == "win32", reason="Demo uses Unix terminal features")
def test_demo_basic_command(assert_demo_output):
    """Test that demo terminal can execute basic commands."""
    assert_demo_output("echo hello world", "hello world")


@pytest.mark.integration
@pytest.mark.skipif(sys.platform == "win32", reason="Demo uses Unix terminal features")
def test_demo_multiple_commands(assert_demo_output):
    """Test demo terminal with multiple commands."""
    assert_demo_output("echo first\r\necho second\r\npwd", ["first", "second"])


@pytest.mark.integration
@pytest.mark.skipif(sys.platform == "win32", reason="Demo uses Unix terminal features")
def test_demo_clean_exit(assert_demo_output):
    """Test that demo exits cleanly."""
    # Just verify exit works - fixture auto-adds exit if missing
    output = assert_demo_output("", [])  # Empty commands, no expected output
    assert isinstance(output, str), "Should return string output"
