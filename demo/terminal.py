#!/usr/bin/env python3
"""
bittty terminal emulator demo.

This demonstrates the clean architectural separation between:
1. bittty: The terminal emulator engine (PTY, parsing, screen state)
2. Frontend: Display rendering and input handling (this demo uses stdout)

This serves as a reference for how other frontends (Qt, web, pygame, etc.)
should interact with the bittty API.
"""

import asyncio
import sys
import termios
import tty
import shutil
import signal
from bittty import Terminal


class StdoutFrontend:
    """
    A minimal frontend that renders bittty terminal content to stdout.

    This demonstrates the proper architectural boundary:
    - Gets screen content from bittty using capture_pane()
    - Handles input by calling bittty's input methods
    - Manages display using basic ANSI escape sequences
    """

    def __init__(self):
        # Get terminal dimensions
        size = shutil.get_terminal_size()
        self.width = size.columns
        self.height = size.lines - 2  # Reserve 2 lines for status/instructions

        # Create the terminal emulator engine
        self.terminal = Terminal(command="/bin/bash", width=self.width, height=self.height)

        self.running = True
        self.old_termios = None

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
        """
        Render the current terminal state to stdout.

        This demonstrates how a frontend gets content from bittty.
        """
        # Move to top-left corner
        print("\033[H", end="")

        # Get complete screen content from bittty
        screen_content = self.terminal.capture_pane()

        # Render each line
        for i, line in enumerate(screen_content.split("\n")):
            if i < self.height:
                # Move to line and print content
                print(f"\033[{i+1}H{line}\033[K", end="")

        # Show status line at bottom
        status = f"bittty demo | {self.width}x{self.height} | Type 'exit' to quit"
        print(f"\033[{self.height+1}H\033[7m{status:<{self.width}}\033[0m", end="", flush=True)

    def handle_input_char(self, char):
        """
        Handle a single input character.

        This demonstrates proper input handling via bittty's API.
        """
        if ord(char) == 3:  # Ctrl+C
            # Let bittty handle Ctrl+C (will send to bash)
            self.terminal.input_key("c", modifier=2)  # KEY_MOD_CTRL = 2
        elif ord(char) == 4:  # Ctrl+D (EOF)
            self.terminal.input(char)
        elif ord(char) == 27:  # ESC - might be escape sequence
            # For this demo, just send ESC directly
            # A full frontend would parse escape sequences for arrow keys, etc.
            self.terminal.input(char)
        else:
            # Regular character
            self.terminal.input(char)

    def handle_pty_data(self, data: str):
        """
        Handle data from the PTY.

        This is called when the terminal process sends output.
        """
        # Feed data to bittty's parser
        self.terminal.parser.feed(data)

        # Re-render the screen
        self.render_screen()

    async def input_loop(self):
        """Handle keyboard input in async loop."""
        loop = asyncio.get_event_loop()

        def read_char():
            try:
                import os

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

    async def main_loop(self):
        """Main demo loop."""
        try:
            self.setup_terminal()

            # Set up bittty to call our handler when PTY data arrives
            self.terminal.set_pty_data_callback(self.handle_pty_data)

            # Start the terminal process
            await self.terminal.start_process()

            # Initial render
            self.render_screen()

            # Start input handling
            input_task = asyncio.create_task(self.input_loop())

            # Main loop - just wait for process to exit
            while self.running:
                await asyncio.sleep(0.1)

                # Check if bash process has exited
                if self.terminal.process and self.terminal.process.poll() is not None:
                    self.running = False
                    break
                elif not self.terminal.process:
                    # Process was never started or already cleaned up
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
        self.terminal.stop_process()
        self.restore_terminal()


def signal_handler(signum, frame):
    """Handle signals gracefully."""
    sys.exit(0)


async def main():
    """Entry point."""
    # Set up signal handling
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Create and run the demo
    frontend = StdoutFrontend()
    await frontend.main_loop()


if __name__ == "__main__":
    asyncio.run(main())
