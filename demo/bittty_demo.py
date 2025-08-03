#!/usr/bin/env python3
"""
BitTTY hardware-inspired terminal emulator demo.

This demonstrates the new modular architecture where devices are plugged
into boards like hardware components, while running a real terminal session.
"""

import asyncio
import shutil
import signal
import sys
from bittty import BitTTY, devices


class BitTTYDemo:
    """
    A demo that shows BitTTY's modular architecture with real TTY devices.
    """

    def __init__(self, configuration="modern"):
        # Get terminal dimensions
        size = shutil.get_terminal_size()
        self.width = size.columns
        self.height = size.lines - 2  # Reserve 2 lines for status

        self.configuration = configuration

        # Create the BitTTY chassis
        self.bittty = BitTTY()

        # Configure devices based on selected configuration
        self.configure_devices()

        self.running = True

    def configure_devices(self):
        """Configure devices based on selected configuration."""
        if self.configuration == "basic":
            self.configure_basic_terminal()
        elif self.configuration == "modern":
            self.configure_modern_terminal()
        elif self.configuration == "teletype":
            self.configure_teletype()
        else:
            self.configure_modern_terminal()

    def configure_basic_terminal(self):
        """Configure a basic terminal with TTY devices."""
        print("Configuring Basic Terminal...")

        # TTY devices for host terminal I/O
        self.tty_input = devices.TTYInputDevice()
        self.tty_monitor = devices.TTYMonitorDevice(self.width, self.height)

        # Connection to child process
        self.connection = devices.ConnectionDevice("/bin/bash")

        # Basic bell
        self.bell = devices.AudioBellDevice()

        # Plug devices into main board
        self.bittty.plug_in(self.tty_input)
        self.bittty.plug_in(self.tty_monitor)
        self.bittty.plug_in(self.connection)
        self.bittty.plug_in(self.bell)

    def configure_modern_terminal(self):
        """Configure a modern terminal with expansion boards."""
        print("Configuring Modern Terminal with Expansion Boards...")

        # TTY devices for host terminal I/O
        self.tty_input = devices.TTYInputDevice()
        self.tty_monitor = devices.TTYMonitorDevice(self.width, self.height)

        # Connection to child process
        self.connection = devices.ConnectionDevice("/bin/bash")

        # Plug core devices into main board
        self.bittty.plug_in(self.tty_input)
        self.bittty.plug_in(self.tty_monitor)
        self.bittty.plug_in(self.connection)

        # Audio expansion board
        from bittty.device import Board

        audio_board = Board(self.bittty.main_board)
        self.bell = devices.VisualBellDevice(audio_board)  # Visual instead of audio

        # Input expansion board (for additional input devices)
        input_board = Board(self.bittty.main_board)
        devices.KeyboardDevice(input_board)  # Virtual keyboard for features
        devices.MouseDevice(input_board)  # Virtual mouse for features

    def configure_teletype(self):
        """Configure a teletype printer simulation."""
        print("Configuring Teletype Printer Simulation...")

        # TTY devices for host terminal I/O
        self.tty_input = devices.TTYInputDevice()
        self.tty_monitor = devices.TTYMonitorDevice(self.width, self.height)

        # Connection to child process
        self.connection = devices.ConnectionDevice("/bin/bash")

        # Line printer for teletype simulation
        self.printer = devices.LinePrinter(72, uppercase_only=True)
        self.bell = devices.AudioBellDevice()  # Mechanical bell simulation

        # Plug devices into main board
        self.bittty.plug_in(self.tty_input)
        self.bittty.plug_in(self.tty_monitor)
        self.bittty.plug_in(self.connection)
        self.bittty.plug_in(self.printer)
        self.bittty.plug_in(self.bell)

    def render_screen(self):
        """Render the current terminal state to the host terminal."""
        # Use TTY monitor to render to host terminal
        self.tty_monitor.render_screen_to_host()

        # Show status line at bottom
        device_names = [d.__class__.__name__ for d in self.bittty.get_devices()]
        status = f"BitTTY {self.configuration} | Devices: {', '.join(device_names)} | {self.width}x{self.height}"
        self.tty_monitor.write_to_host_terminal(f"\033[{self.height+1}H\033[7m{status:<{self.width}}\033[0m")

    def handle_input_char(self, char):
        """Handle a single input character."""
        # Send input through BitTTY's input methods
        char_code = ord(char)

        if char_code == 3:  # Ctrl+C
            self.bittty.input_key("c", 2)  # KEY_MOD_CTRL = 2
        elif char_code == 4:  # Ctrl+D (EOF)
            self.bittty.input(char)
        elif char_code == 27:  # ESC - might be escape sequence
            self.bittty.input(char)
        else:
            # Regular character
            self.bittty.input(char)

    def handle_pty_data(self, data: str):
        """Handle data from the PTY."""
        # Feed data to BitTTY's parser
        self.bittty.feed(data)

        # Re-render the screen
        self.render_screen()

    async def input_loop(self):
        """Handle keyboard input in async loop."""
        while self.running:
            try:
                # Use TTY input device to read characters
                char = self.tty_input.read_input_char()
                if char:
                    self.handle_input_char(char)
                await asyncio.sleep(0.01)
            except Exception as e:
                print(f"Input error: {e}")
                break

    async def main_loop(self):
        """Main demo loop."""
        try:
            # Set up TTY devices
            self.tty_input.setup_raw_mode()
            self.tty_monitor.setup_screen()

            # Set up BitTTY to call our handler when PTY data arrives
            self.connection.set_pty_data_callback(self.handle_pty_data)

            # Start the terminal process
            await self.connection.start_process()

            # Initial render
            self.render_screen()

            # Start input handling
            input_task = asyncio.create_task(self.input_loop())

            # Main loop - wait for process to exit
            while self.running:
                await asyncio.sleep(0.1)

                # Check if bash process has exited
                if self.connection.process and self.connection.process.poll() is not None:
                    self.running = False
                    break
                elif not self.connection.process:
                    self.running = False
                    break

            input_task.cancel()

        except KeyboardInterrupt:
            pass
        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up resources."""
        self.running = False
        if hasattr(self, "connection"):
            self.connection.stop_process()
        if hasattr(self, "tty_input"):
            self.tty_input.cleanup()
        if hasattr(self, "tty_monitor"):
            self.tty_monitor.cleanup()


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

Starting terminal session with {args.config} configuration...
""")

    await asyncio.sleep(1)

    # Create and run the demo
    demo = BitTTYDemo(args.config)
    await demo.main_loop()


if __name__ == "__main__":
    asyncio.run(main())
