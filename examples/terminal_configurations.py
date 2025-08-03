#!/usr/bin/env python3
"""
BitTTY Terminal Configuration Examples

This file demonstrates different ways to configure BitTTY using the
hardware-inspired device and board architecture.
"""

import sys

sys.path.insert(0, "../src")

from bittty import BitTTY, devices
from bittty.device import Board


def create_basic_vt100():
    """Create a basic VT100-compatible terminal.

    This configuration mimics a classic VT100 terminal with:
    - Monochrome monitor
    - Audio bell
    - Basic keyboard
    """
    tty = BitTTY()

    # Basic VT100 devices
    tty.plug_in(devices.MonitorDevice(80, 24))
    tty.plug_in(devices.AudioBellDevice())

    return tty


def create_modern_gui_terminal():
    """Create a modern GUI terminal with expansion boards.

    This shows how modern terminals can be built with specialized boards
    for different functions, similar to PC expansion cards.
    """
    tty = BitTTY()

    # Video expansion board
    video_board = Board(tty.main_board)
    monitor = devices.MonitorDevice(120, 40, video_board)  # Large screen

    # Audio expansion board
    audio_board = Board(video_board)  # Nested board
    devices.VisualBellDevice(audio_board)  # Visual flash instead of sound

    # Input expansion board
    input_board = Board(tty.main_board)
    devices.KeyboardDevice(input_board)
    devices.MouseDevice(input_board)

    return tty


def create_teletype_asr33():
    """Create a 1960s ASR-33 Teletype simulation.

    This configuration emulates the classic ASR-33 Teletype:
    - 72-character line printer
    - Uppercase-only output
    - Mechanical bell
    - 110 baud connection
    """
    tty = BitTTY()

    # ASR-33 components
    tty.plug_in(devices.LinePrinter(width=72, uppercase_only=True))
    tty.plug_in(devices.AudioBellDevice())  # Mechanical bell simulation

    return tty


def create_debug_terminal():
    """Create a terminal with debug and logging capabilities.

    This configuration adds debugging devices that can log
    commands and record sessions.
    """
    tty = BitTTY()

    # Main terminal
    tty.plug_in(devices.MonitorDevice(80, 24))
    tty.plug_in(devices.SilentBellDevice())  # No noise during debugging

    # Debug expansion board
    debug_board = Board(tty.main_board)
    # Future: CommandLogger, SequenceRecorder devices would go here

    return tty


def create_multi_session_terminal():
    """Create a terminal that can handle multiple sessions.

    This shows how the board architecture could support multiple
    concurrent terminal sessions.
    """
    tty = BitTTY()

    # Session 1 board
    session1_board = Board(tty.main_board)
    devices.MonitorDevice(80, 24, session1_board)

    # Session 2 board
    session2_board = Board(tty.main_board)
    devices.MonitorDevice(80, 24, session2_board)

    # Shared audio
    tty.plug_in(devices.AudioBellDevice())

    return tty


def create_accessibility_terminal():
    """Create a terminal optimized for accessibility.

    This configuration includes devices that help with
    screen reading and accessibility features.
    """
    tty = BitTTY()

    # High contrast monitor
    tty.plug_in(devices.MonitorDevice(80, 24))

    # Visual bell for hearing impaired
    tty.plug_in(devices.VisualBellDevice())

    # Accessibility board
    accessibility_board = Board(tty.main_board)
    # Future: ScreenReader, BrailleOutput devices would go here

    return tty


def create_embedded_terminal():
    """Create a minimal terminal for embedded systems.

    This configuration uses the minimum devices needed for
    basic terminal functionality.
    """
    tty = BitTTY()

    # Minimal configuration
    tty.plug_in(devices.MonitorDevice(40, 16))  # Small screen
    tty.plug_in(devices.SilentBellDevice())  # No audio

    return tty


def create_graphics_terminal():
    """Create a terminal with graphics capabilities.

    This configuration could support graphics protocols like
    Sixel, ReGIS, or Tektronix graphics.
    """
    tty = BitTTY()

    # Graphics-capable monitor
    tty.plug_in(devices.MonitorDevice(132, 50))  # Wide screen
    tty.plug_in(devices.AudioBellDevice())

    # Graphics board
    graphics_board = Board(tty.main_board)
    # Future: SixelRenderer, ReGISRenderer devices would go here

    return tty


def demonstrate_configurations():
    """Demonstrate all the different configurations."""
    configurations = {
        "Basic VT100": create_basic_vt100,
        "Modern GUI Terminal": create_modern_gui_terminal,
        "ASR-33 Teletype": create_teletype_asr33,
        "Debug Terminal": create_debug_terminal,
        "Multi-session Terminal": create_multi_session_terminal,
        "Accessibility Terminal": create_accessibility_terminal,
        "Embedded Terminal": create_embedded_terminal,
        "Graphics Terminal": create_graphics_terminal,
    }

    for name, create_func in configurations.items():
        print(f"\n{name}:")
        print("=" * (len(name) + 1))

        tty = create_func()
        device_names = [d.__class__.__name__ for d in tty.get_devices()]

        print(f"Devices: {device_names}")

        # Query capabilities
        screen_sizes = tty.query("screen_size")
        if screen_sizes:
            print(f"Screen size: {screen_sizes[0]}")

        # Test basic functionality
        tty.feed("Hello World!")
        monitors = tty.get_devices(devices.MonitorDevice)
        if monitors:
            content = monitors[0].capture_pane()
            print(f"Sample output: {repr(content[:20])}...")


if __name__ == "__main__":
    demonstrate_configurations()
