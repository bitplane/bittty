#!/usr/bin/env python3
"""
BitTTY hardware-inspired terminal emulator demo.

This demonstrates the new modular architecture where devices are plugged
into boards like hardware components. The demo shows different configurations:
1. Basic VT100 terminal
2. Modern terminal with expansion boards
3. Teletype printer simulation
"""

import asyncio
import os
import sys
import termios
import tty
import shutil
import signal
from bittty import BitTTY, devices
from bittty.device import Board


class BitTTYStdoutFrontend:
    """
    A frontend that demonstrates the new BitTTY modular architecture.

    This shows how to configure different terminal types by plugging
    different devices into boards.
    """

    def __init__(self, configuration="modern"):
        # Get terminal dimensions
        size = shutil.get_terminal_size()
        self.width = size.columns
        self.height = size.lines - 3  # Reserve 3 lines for status

        self.configuration = configuration

        # Create the BitTTY chassis
        self.bittty = BitTTY()

        # Configure devices based on selected configuration
        self.configure_devices()

        self.running = True
        self.old_termios = None

    def configure_devices(self):
        """Configure devices based on selected configuration."""
        if self.configuration == "basic":
            self.configure_basic_vt100()
        elif self.configuration == "modern":
            self.configure_modern_terminal()
        elif self.configuration == "teletype":
            self.configure_teletype()
        else:
            self.configure_modern_terminal()

    def configure_basic_vt100(self):
        """Configure a basic VT100-style terminal."""
        print("Configuring Basic VT100 Terminal...")

        # Basic devices directly on main board
        self.monitor = devices.MonitorDevice(self.width, self.height)
        self.bell = devices.AudioBellDevice()

        # For demo purposes, no actual PTY connection

        self.bittty.plug_in(self.monitor)
        self.bittty.plug_in(self.bell)

        print(f"Configuration: {self.bittty}")

    def configure_modern_terminal(self):
        """Configure a modern terminal with expansion boards."""
        print("Configuring Modern Terminal with Expansion Boards...")

        # Video expansion board
        video_board = Board(self.bittty.main_board)
        self.monitor = devices.MonitorDevice(self.width, self.height, video_board)

        # Audio expansion board
        audio_board = Board(self.bittty.main_board)
        self.bell = devices.VisualBellDevice(audio_board)  # Visual instead of audio

        # Input expansion board
        input_board = Board(self.bittty.main_board)
        keyboard = devices.KeyboardDevice(input_board)
        mouse = devices.MouseDevice(input_board)

        print(f"Configuration: {self.bittty}")
        print("Expansion boards:")
        print(f"  Video Board: {[d.__class__.__name__ for d in video_board.devices]}")
        print(f"  Audio Board: {[d.__class__.__name__ for d in audio_board.devices]}")
        print(f"  Input Board: {[d.__class__.__name__ for d in input_board.devices]}")

    def configure_teletype(self):
        """Configure a teletype printer simulation."""
        print("Configuring Teletype Printer Simulation...")

        # Line printer instead of monitor
        self.printer = devices.LinePrinter(72, uppercase_only=True)  # 72 char ASR-33
        self.bell = devices.AudioBellDevice()  # Mechanical bell

        self.bittty.plug_in(self.printer)
        self.bittty.plug_in(self.bell)

        # For teletype, we'll use the printer's output
        self.monitor = None

        print(f"Configuration: {self.bittty}")

    def setup_terminal(self):
        """Set up raw terminal mode for proper input handling."""
        self.old_termios = termios.tcgetattr(sys.stdin.fileno())
        tty.setraw(sys.stdin.fileno())

        # Hide cursor and clear screen
        print("\033[?25l\033[2J\033[H", end="", flush=True)

    def restore_terminal(self):
        """Restore original terminal settings."""
        if self.old_termios:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.old_termios)
        # Show cursor and clear screen
        print("\033[?25h\033[2J\033[H", end="", flush=True)

    def render_screen(self):
        """Render the current terminal state to stdout."""
        # Move to top-left corner
        print("\033[H", end="")

        if self.monitor:
            # Get complete screen content from monitor device
            screen_content = self.monitor.capture_pane()

            # Render each line
            for i, line in enumerate(screen_content.split("\n")):
                if i < self.height:
                    # Move to line and print content
                    print(f"\033[{i+1}H{line}\033[K", end="")
        else:
            # For teletype mode, show a simulation message
            print(f"\033[1H{'TELETYPE MODE - Output goes to printer':<{self.width}}\033[K", end="")
            print(f"\033[2H{'(This is a simulation - no actual output shown)':<{self.width}}\033[K", end="")

        # Show device information
        device_info = f"Devices: {[d.__class__.__name__ for d in self.bittty.get_devices()]}"
        config_info = f"Config: {self.configuration} | Size: {self.width}x{self.height}"
        instructions = "Type text and escape sequences | Ctrl+Q to quit | Ctrl+C for demo commands"

        print(f"\033[{self.height+1}H\033[7m{device_info:<{self.width}}\033[0m", end="")
        print(f"\033[{self.height+2}H\033[7m{config_info:<{self.width}}\033[0m", end="")
        print(f"\033[{self.height+3}H\033[7m{instructions:<{self.width}}\033[0m", end="", flush=True)

    def handle_input_char(self, char):
        """Handle a single input character."""
        if ord(char) == 17:  # Ctrl+Q
            self.running = False
            return
        elif ord(char) == 3:  # Ctrl+C - show demo commands
            self.show_demo_commands()
            return

        # Feed character to BitTTY for processing
        self.bittty.feed(char)

        # Re-render after processing
        self.render_screen()

    def show_demo_commands(self):
        """Show some demo escape sequences."""
        demo_sequences = [
            ("Hello World", "Basic text"),
            ("\x1b[1;31mRed Bold Text\x1b[0m", "Red bold text with reset"),
            ("\x1b[10;20HPositioned", "Cursor positioning"),
            ("\x1b[2JClear", "Clear screen"),
            ("\x07", "Bell"),
            ("\x1b[?1047h\x1b[1;1HAlt Screen\x1b[?1047l", "Alternate screen demo"),
        ]

        for sequence, description in demo_sequences:
            print(f"\nDemo: {description}")
            self.bittty.feed(sequence)
            self.render_screen()
            await asyncio.sleep(1)

    async def demo_loop(self):
        """Run interactive demo without PTY."""
        try:
            self.setup_terminal()

            # Initial render
            self.render_screen()

            # Show welcome message
            welcome = "Welcome to BitTTY! Try typing some text or escape sequences."
            self.bittty.feed(welcome)
            self.render_screen()

            # Input loop
            loop = asyncio.get_event_loop()

            def read_char():
                try:
                    data = os.read(sys.stdin.fileno(), 1)
                    return data.decode("utf-8", errors="replace")
                except (OSError, BlockingIOError):
                    return None

            while self.running:
                try:
                    char = await loop.run_in_executor(None, read_char)
                    if char:
                        self.handle_input_char(char)
                    await asyncio.sleep(0.01)
                except Exception:
                    break

        except KeyboardInterrupt:
            pass
        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up resources."""
        self.running = False
        self.restore_terminal()


def signal_handler(signum, frame):
    """Handle signals gracefully."""
    sys.exit(0)


async def main():
    """Entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="BitTTY hardware-inspired terminal demo")
    parser.add_argument(
        "--config", choices=["basic", "modern", "teletype"], default="modern", help="Terminal configuration"
    )
    args = parser.parse_args()

    # Set up signal handling
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print(f"""
BitTTY Hardware-Inspired Terminal Emulator Demo
===============================================

Configuration: {args.config}

This demo shows how BitTTY works as a modular system where devices
are plugged into boards like hardware components.

The demo will start an interactive session where you can:
- Type text and see it rendered
- Try escape sequences like \\x1b[1;31m for colors
- Use Ctrl+C to run automated demos
- Use Ctrl+Q to quit

Starting demo...
""")

    await asyncio.sleep(2)

    # Create and run the demo
    frontend = BitTTYStdoutFrontend(args.config)
    await frontend.demo_loop()


if __name__ == "__main__":
    asyncio.run(main())
