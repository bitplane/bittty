"""Basic tests for tcaps (terminal capabilities) functionality."""

from bittty.tcaps import TermInfo


def test_terminfo_init():
    """Test TermInfo initialization."""
    # Should be able to create instance without error
    terminfo = TermInfo("xterm", "")
    assert terminfo is not None
    assert terminfo.name == "xterm"


def test_terminfo_with_overrides():
    """Test TermInfo with override string."""
    # Should handle override string without error
    terminfo = TermInfo("xterm", "cols=120:lines=40")
    assert terminfo is not None


def test_has_capability():
    """Test checking for terminal capabilities."""
    terminfo = TermInfo("xterm", "")

    # Should be able to call method without error (returns None currently)
    result = terminfo.has("colors")
    assert result is None


def test_get_string_capability():
    """Test getting string capabilities."""
    terminfo = TermInfo("xterm", "")

    # Should be able to call method without error
    result = terminfo.get_string("cup")
    assert result is None


def test_get_number_capability():
    """Test getting numeric capabilities."""
    terminfo = TermInfo("xterm", "")

    # Should be able to call method without error
    result = terminfo.get_number("cols")
    assert result is None


def test_get_flag_capability():
    """Test getting boolean flag capabilities."""
    terminfo = TermInfo("xterm", "")

    # Should be able to call method without error
    result = terminfo.get_flag("am")
    assert result is None


def test_describe():
    """Test terminal description."""
    terminfo = TermInfo("xterm", "")

    # Should be able to call method without error
    result = terminfo.describe()
    assert result is None
