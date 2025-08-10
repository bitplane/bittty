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
import os
import sys
import shutil
import platform
from bittty import Terminal

try:
    import termios
    import tty
    import signal

    HAS_UNIX_TERMIOS = True
except ImportError:
    HAS_UNIX_TERMIOS = False
    import signal

try:
    import msvcrt

    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False


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

        self.is_windows = platform.system() == "Windows"
        command = self.get_default_shell()
        # Create the terminal emulator engine
        self.terminal = Terminal(command=command, width=self.width, height=self.height)

        self.running = True
        self.old_termios = None

    def get_default_shell(self):
        """Get the default shell command for the current platform."""
        if self.is_windows:
            # Try PowerShell first, then fallback to cmd
            if shutil.which("pwsh"):
                return "pwsh"
            elif shutil.which("powershell"):
                return "powershell"
            else:
                return "cmd"
        else:
            # Try to find user's preferred shell
            shell = os.environ.get("SHELL")
            if shell and shutil.which(shell):
                return shell
            for shell in ["/bin/bash", "/bin/sh", "/usr/bin/bash"]:
                if os.path.exists(shell):
                    return shell
            return "sh"  # Final fallback

    def setup_terminal(self):
        """Set up raw terminal mode for proper input handling."""
        if HAS_UNIX_TERMIOS:
            try:
                self.old_termios = termios.tcgetattr(sys.stdin.fileno())
                tty.setraw(sys.stdin.fileno())
            except (termios.error, OSError):
                # Running in non-interactive environment, skip terminal setup
                self.old_termios = None
        elif self.is_windows and HAS_MSVCRT:
            pass

        # Hide cursor and clear screen
        print("\033[?25l\033[2J\033[H", end="", flush=True)

    def restore_terminal(self):
        """Restore original terminal settings."""
        if HAS_UNIX_TERMIOS and self.old_termios:
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
        status = f"bittty demo | {self.width}x{self.height} | exit normally to quit"
        print(f"\033[{self.height+1}H\033[7m{status:<{self.width}}\033[0m", end="", flush=True)

    def handle_input_char(self, char):
        """
        Handle a single input character.

        This demonstrates proper input handling via bittty's API.
        """
        if ord(char) == 4:  # Ctrl+D (EOF)
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
                if self.is_windows and HAS_MSVCRT:
                    if msvcrt.kbhit():
                        char = msvcrt.getch()
                        if isinstance(char, bytes):
                            return char.decode("utf-8", errors="replace")
                        return char
                    return None
                else:
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
                await asyncio.sleep(0.01)  # Check more frequently

                # Check if shell process has exited
                if self.terminal.process and self.terminal.process.poll() is not None:
                    self.running = False
                    break
                elif not self.terminal.process:
                    # Process was never started or already cleaned up
                    self.running = False
                    break

            # Cancel input task immediately when process exits
            input_task.cancel()
            try:
                await input_task
            except asyncio.CancelledError:
                pass

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


def sigwinch_handler(signum, frame):
    """Handle terminal resize signals."""
    # This will be set by main() to reference the frontend instance
    if hasattr(sigwinch_handler, "frontend"):
        frontend = sigwinch_handler.frontend
        # Get new terminal size
        size = shutil.get_terminal_size()
        new_width = size.columns
        new_height = size.lines - 2  # Reserve 2 lines for status/instructions

        # Update frontend dimensions
        frontend.width = new_width
        frontend.height = new_height

        # Resize the terminal emulator
        frontend.terminal.resize(new_width, new_height)


async def main():
    """Entry point."""
    # Set up signal handling
    signal.signal(signal.SIGINT, signal_handler)

    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, signal_handler)

    # Set up resize signal handling (Unix only)
    if hasattr(signal, "SIGWINCH"):
        signal.signal(signal.SIGWINCH, sigwinch_handler)

    # Create and run the demo
    frontend = StdoutFrontend()

    # Make frontend available to signal handler
    sigwinch_handler.frontend = frontend

    await frontend.main_loop()


if __name__ == "__main__":
    asyncio.run(main())
