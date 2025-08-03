"""Integration tests for the new BitTTY architecture.

These tests verify that the modular device-based architecture
works correctly and maintains compatibility with existing functionality.
"""

from bittty import BitTTY, devices, Command, Terminal
from bittty.command import command_to_escape


def test_basic_bittty_creation():
    """Test basic BitTTY creation and device plugging."""
    tty = BitTTY()

    # Plug in basic devices
    monitor = devices.MonitorDevice(80, 24)
    bell = devices.AudioBellDevice()

    tty.attach(monitor)
    tty.attach(bell)

    # Check devices were plugged in
    plugged_devices = tty.get_devices()
    assert len(plugged_devices) == 2
    assert any(isinstance(d, devices.MonitorDevice) for d in plugged_devices)
    assert any(isinstance(d, devices.AudioBellDevice) for d in plugged_devices)


def test_text_output():
    """Test basic text output through the new architecture."""
    tty = BitTTY()
    monitor = devices.MonitorDevice(80, 24)
    tty.attach(monitor)

    # Feed some text
    tty.feed("Hello World")

    # Check it was written to the monitor
    content = monitor.capture_pane()
    assert "Hello World" in content
    assert monitor.cursor_x == 11  # After "Hello World"
    assert monitor.cursor_y == 0


def test_cursor_movement():
    """Test cursor movement commands."""
    tty = BitTTY()
    monitor = devices.MonitorDevice(80, 24)
    tty.attach(monitor)

    # Move cursor to position 10,5 (ESC[6;11H - 1-based coordinates)
    tty.feed("\x1b[6;11H")

    assert monitor.cursor_x == 10  # 0-based
    assert monitor.cursor_y == 5  # 0-based


def test_bell_handling():
    """Test bell command handling."""
    tty = BitTTY()
    bell = devices.AudioBellDevice()
    tty.attach(bell)

    # Send bell character
    tty.feed("\x07")

    # Check bell was triggered
    assert bell.bell_count == 1


def test_color_sequences():
    """Test SGR color sequences."""
    tty = BitTTY()
    monitor = devices.MonitorDevice(80, 24)
    tty.attach(monitor)

    # Set bold red text
    tty.feed("\x1b[1;31mHello")

    # Check ANSI code was set
    assert "\x1b[1;31m" in monitor.current_ansi_code


def test_screen_clearing():
    """Test screen clearing commands."""
    tty = BitTTY()
    monitor = devices.MonitorDevice(80, 24)
    tty.attach(monitor)

    # Write some text
    tty.feed("Hello World")

    # Clear screen
    tty.feed("\x1b[2J")

    # Check screen is cleared
    content = monitor.capture_pane()
    assert content.strip() == ""


def test_device_communication():
    """Test devices communicating through the board."""
    tty = BitTTY()
    monitor = devices.MonitorDevice(80, 24)
    bell = devices.AudioBellDevice()

    tty.attach(monitor)
    tty.attach(bell)

    # Send combined sequence (text + bell)
    tty.feed("Hello\x07World")

    # Check both devices handled their parts
    content = monitor.capture_pane()
    assert "HelloWorld" in content
    assert bell.bell_count == 1


def test_scroll_region():
    """Test scroll region functionality."""
    tty = BitTTY()
    monitor = devices.MonitorDevice(80, 24)
    tty.attach(monitor)

    # Set scroll region from line 5 to 15 (ESC[6;16r - 1-based)
    tty.feed("\x1b[6;16r")

    assert monitor.scroll_top == 5  # 0-based
    assert monitor.scroll_bottom == 15  # 0-based


def test_alternate_screen():
    """Test alternate screen buffer switching."""
    tty = BitTTY()
    monitor = devices.MonitorDevice(80, 24)
    tty.attach(monitor)

    # Write to primary screen
    tty.feed("Primary")

    # Switch to alternate screen
    tty.feed("\x1b[?1047h")

    assert monitor.in_alt_screen

    # Write to alternate screen
    tty.feed("Alternate")

    # Switch back to primary
    tty.feed("\x1b[?1047l")

    assert not monitor.in_alt_screen

    # Check primary screen content is restored
    content = monitor.capture_pane()
    assert "Primary" in content


def test_character_sets():
    """Test character set switching."""
    tty = BitTTY()
    monitor = devices.MonitorDevice(80, 24)
    tty.attach(monitor)

    # Set G0 to DEC special graphics
    tty.feed("\x1b(0")

    assert monitor.g0_charset == "0"

    # Set G1 to UK character set
    tty.feed("\x1b)A")

    assert monitor.g1_charset == "A"


def test_query_capabilities():
    """Test device capability queries."""
    tty = BitTTY()
    monitor = devices.MonitorDevice(80, 24)
    bell = devices.AudioBellDevice()

    tty.attach(monitor)
    tty.attach(bell)

    # Query screen size
    screen_sizes = tty.query("screen_size")
    assert (80, 24) in screen_sizes

    # Query bell support
    bell_support = tty.query("bell_supported")
    assert True in bell_support


def test_board_hierarchy():
    """Test device attachment to BitTTY board."""
    tty = BitTTY()

    # Attach devices directly to BitTTY
    monitor = devices.MonitorDevice(80, 24)
    bell = devices.AudioBellDevice()

    tty.attach(monitor)
    tty.attach(bell)

    # Test that commands are routed correctly
    tty.feed("Hello\x07")

    content = monitor.capture_pane()
    assert "Hello" in content
    assert bell.bell_count == 1


def test_command_to_escape_conversion():
    """Test command to escape sequence conversion."""

    # Test CSI command
    cmd = Command("CSI_CUP", "CSI", (10, 20), "H")
    escape_seq = command_to_escape(cmd)
    assert escape_seq == "\x1b[10;20H"

    # Test C0 command
    cmd = Command("C0_BEL", "C0", (), None)
    escape_seq = command_to_escape(cmd)
    assert escape_seq == "\x07"

    # Test text command
    cmd = Command("TEXT", "TEXT", ("Hello",), None)
    escape_seq = command_to_escape(cmd)
    assert escape_seq == "Hello"


def test_backward_compatibility():
    """Test that old Terminal class still works."""

    # Create old-style terminal
    terminal = Terminal(width=80, height=24)

    # Test basic functionality
    terminal.write_text("Hello")
    assert terminal.cursor_x == 5

    terminal.move_cursor(10, 5)
    assert terminal.cursor_x == 10
    assert terminal.cursor_y == 5
