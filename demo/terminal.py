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
        self.old_stdin_blocking = None
        self.host_mouse_mode = None
        self.input_sequence_buffer = ""

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
                self.old_stdin_blocking = os.get_blocking(sys.stdin.fileno())
                self.old_termios = termios.tcgetattr(sys.stdin.fileno())
                tty.setraw(sys.stdin.fileno())
            except (termios.error, OSError):
                # Running in non-interactive environment, skip terminal setup
                self.old_termios = None
            try:
                if self.old_stdin_blocking is None:
                    self.old_stdin_blocking = os.get_blocking(sys.stdin.fileno())
                os.set_blocking(sys.stdin.fileno(), False)
            except OSError:
                self.old_stdin_blocking = None
        elif self.is_windows and HAS_MSVCRT:
            pass

        # Hide cursor and clear screen
        print("\033[?25l\033[2J\033[H", end="", flush=True)

    def restore_terminal(self):
        """Restore original terminal settings."""
        self.disable_host_mouse()
        if HAS_UNIX_TERMIOS and self.old_termios:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.old_termios)
        if self.old_stdin_blocking is not None:
            try:
                os.set_blocking(sys.stdin.fileno(), self.old_stdin_blocking)
            except OSError:
                pass
        # Show cursor and clear screen
        print("\033[?25h\033[2J\033[H", end="", flush=True)

    def disable_host_mouse(self):
        """Disable host-terminal mouse reporting modes used by the demo."""
        if self.host_mouse_mode is not None:
            print("\033[?1000l\033[?1002l\033[?1003l\033[?1006l", end="", flush=True)
            self.host_mouse_mode = None

    def sync_host_mouse(self):
        """Mirror bittty's requested mouse mode onto the host terminal."""
        if self.terminal.mouse_any_tracking:
            mode = "any"
            enable = "\033[?1003h\033[?1006h"
        elif self.terminal.mouse_button_tracking:
            mode = "button"
            enable = "\033[?1002h\033[?1006h"
        elif self.terminal.mouse_tracking:
            mode = "basic"
            enable = "\033[?1000h\033[?1006h"
        else:
            mode = None
            enable = ""

        if mode == self.host_mouse_mode:
            return

        self.disable_host_mouse()
        if mode is not None:
            print(enable, end="", flush=True)
            self.host_mouse_mode = mode

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

        # Child output may have changed mouse reporting modes.
        self.sync_host_mouse()

        # Re-render the screen
        self.render_screen()

    def handle_sgr_mouse_sequence(self, sequence: str) -> bool:
        """Parse host SGR mouse reports and forward them through bittty."""
        if not sequence.startswith("\033[<") or sequence[-1] not in "Mm":
            return False

        try:
            button_s, x_s, y_s = sequence[3:-1].split(";")
            button = int(button_s)
            x = int(x_s)
            y = int(y_s)
        except ValueError:
            return False

        modifiers = set()
        if button & 4:
            modifiers.add("shift")
        if button & 8:
            modifiers.add("meta")
        if button & 16:
            modifiers.add("ctrl")

        event_type = "release" if sequence[-1] == "m" else "press"
        base_button = button & ~(4 | 8 | 16)
        if base_button & 32:
            event_type = "move"
            base_button &= ~32

        self.terminal.input_mouse(x, y, base_button, event_type, modifiers)
        return True

    def handle_input(self, char):
        """Handle keyboard input, buffering complete SGR mouse sequences."""
        if self.input_sequence_buffer:
            self.input_sequence_buffer += char
            if "\033[<".startswith(self.input_sequence_buffer):
                return
            if self.input_sequence_buffer.startswith("\033[<"):
                if self.input_sequence_buffer[-1] in "Mm":
                    sequence = self.input_sequence_buffer
                    self.input_sequence_buffer = ""
                    if not self.handle_sgr_mouse_sequence(sequence):
                        self.terminal.input(sequence)
                return
            self.terminal.input(self.input_sequence_buffer)
            self.input_sequence_buffer = ""
            return

        if char == "\033":
            self.input_sequence_buffer = char
            return

        self.handle_input_char(char)

    async def input_loop(self):
        """Handle keyboard input in async loop."""

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
                    if data == b"":
                        return ""
                    return data.decode("utf-8", errors="replace")
            except (OSError, BlockingIOError):
                return None

        while self.running:
            try:
                char = read_char()
                if char == "":
                    self.running = False
                    break
                elif char:
                    self.handle_input(char)
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
