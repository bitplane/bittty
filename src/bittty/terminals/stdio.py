"""StdioTerminal: the reference terminal, whose venue is this process's stdio.

Composes a Board (never subclasses it) and drives the real outer terminal:
raw-mode stdin, ANSI rendering to stdout, resize handling, and mouse mirroring.
Discrete side-effects arrive through the Terminal hooks (on_bell/on_title/
on_mouse_mode).
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import select
import shutil
import signal
import sys

from ..devices.board import Board
from .base import Terminal
from .probe import probe_caps

try:
    import termios
    import tty

    HAS_UNIX_TERMIOS = True
except ImportError:
    HAS_UNIX_TERMIOS = False

try:
    import msvcrt

    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False

logger = logging.getLogger(__name__)

# Host mouse-tracking enable strings (always paired with SGR 1006 so the reports
# we intercept are in the SGR form handle_sgr_mouse_sequence parses).
_HOST_MOUSE_ENABLE = {
    "any": "\033[?1003h\033[?1006h",
    "button": "\033[?1002h\033[?1006h",
    "basic": "\033[?1000h\033[?1006h",
}


class StdioTerminal(Terminal):
    """Render a bittty Board to the real terminal this program is running in."""

    def __init__(self) -> None:
        size = shutil.get_terminal_size()
        self.width = size.columns
        self.height = size.lines - 2  # reserve 2 lines for the status/instructions
        self.is_windows = platform.system() == "Windows"
        board = Board(command=self.get_default_shell(), width=self.width, height=self.height)
        super().__init__(board)
        self.attach()

        self.running = True
        self.old_termios = None
        self.host_mouse_mode: str | None = None
        self.input_sequence_buffer = ""
        self.dirty = False  # PTY data arrived; the run loop repaints on its tick

    def get_default_shell(self) -> str:
        """Get the default shell command for the current platform."""
        if self.is_windows:
            if shutil.which("pwsh"):
                return "pwsh"
            if shutil.which("powershell"):
                return "powershell"
            return "cmd"
        shell = os.environ.get("SHELL")
        if shell and shutil.which(shell):
            return shell
        for shell in ["/bin/bash", "/bin/sh", "/usr/bin/bash"]:
            if os.path.exists(shell):
                return shell
        return "sh"

    # --- Display hooks (present events) --- #

    def on_bell(self) -> None:
        """Ring the outer terminal's bell."""
        print("\a", end="", flush=True)

    def on_title(self, title: str, icon_title: str) -> None:
        """Mirror the window title onto the outer terminal."""
        print(f"\033]2;{title}\007", end="", flush=True)

    def on_mouse_mode(self, mode: str, sgr: bool) -> None:
        """Mirror the child's requested mouse-tracking mode onto the outer terminal."""
        if mode == "off":
            self.disable_host_mouse()
            return
        if mode == self.host_mouse_mode:
            return
        self.disable_host_mouse()
        print(_HOST_MOUSE_ENABLE[mode], end="", flush=True)
        self.host_mouse_mode = mode
        logger.debug("Enabled host mouse mode: %s", mode)

    def disable_host_mouse(self) -> None:
        """Turn off host-terminal mouse reporting."""
        if self.host_mouse_mode is not None:
            print("\033[?1000l\033[?1002l\033[?1003l\033[?1006l", end="", flush=True)
            self.host_mouse_mode = None

    # --- terminal setup / teardown --- #

    def setup_terminal(self) -> None:
        """Put the host terminal into raw mode, clear it, and ask for focus events."""
        logger.info("Setting up terminal: %sx%s", self.width, self.height)
        if HAS_UNIX_TERMIOS:
            try:
                self.old_termios = termios.tcgetattr(sys.stdin.fileno())
                tty.setraw(sys.stdin.fileno())
            except (termios.error, OSError):
                logger.info("Raw terminal mode unavailable; continuing without it", exc_info=True)
                self.old_termios = None
        # ?1004: the host reports focus in/out (CSI I / CSI O) — drives our own
        # software cursor and is forwarded to a child that enabled 1004 itself.
        print("\033[?25l\033[?1004h\033[2J\033[H", end="", flush=True)

    def restore_terminal(self) -> None:
        """Restore the host terminal to its original state."""
        logger.info("Restoring terminal")
        self.disable_host_mouse()
        if HAS_UNIX_TERMIOS and self.old_termios:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.old_termios)
        print("\033[?1004l\033[?25h\033[2J\033[H", end="", flush=True)

    # --- rendering --- #

    def probe_capabilities(self) -> None:
        """Ask the outer terminal what it can do and push TerminalCaps to the backend."""

        def write(data: str) -> None:
            sys.stdout.write(data)
            sys.stdout.flush()

        try:
            fd = sys.stdin.fileno()
        except (OSError, ValueError):
            fd = None
        caps = probe_caps(fd, write, os.environ)
        self.set_caps(caps)
        logger.info("Display caps: %s", caps)

    def render_screen(self) -> None:
        """Render the current terminal state to stdout."""
        print("\033[H", end="")
        for i, line in enumerate(self.board.capture_pane().split("\n")):
            if i < self.height:
                print(f"\033[{i + 1}H{line}\033[K", end="")
        status = f"bittty demo | {self.width}x{self.height} | exit normally to quit"
        print(f"\033[{self.height + 1}H\033[7m{status:<{self.width}}\033[0m", end="", flush=True)

    def handle_pty_data(self, data: str) -> None:
        """Feed child output into the emulator and mark the screen dirty.

        Rendering happens on the run loop's tick, not per PTY chunk — a repaint
        per chunk backpressures a flooding child (it blocks writing to the PTY
        while we paint), turning a 66ms `find` into a 750ms one.
        """
        try:
            self.board.parser.feed(data)
            self.dirty = True
        except Exception:
            logger.exception("Error handling PTY data: %r", data[-200:])
            raise

    # --- input: mouse interception + forwarding --- #

    def handle_sgr_mouse_sequence(self, sequence: str) -> bool:
        """Parse a host SGR mouse report and re-inject it through bittty."""
        if not sequence.startswith("\033[<") or sequence[-1] not in "Mm":
            return False
        try:
            button_s, x_s, y_s = sequence[3:-1].split(";")
            button, x, y = int(button_s), int(x_s), int(y_s)
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

        self.board.display.input_mouse(x, y, base_button, event_type, modifiers)
        return True

    def handle_focus(self, focused: bool) -> None:
        """A host focus event: the backend owns the state; we just repaint."""
        if focused:
            self.board.display.focus_in()
        else:
            self.board.display.focus_out()
        self.dirty = True

    def handle_input(self, data: str) -> None:
        """Forward host input to bittty, intercepting SGR mouse reports and focus events."""
        stream = self.input_sequence_buffer + data
        self.input_sequence_buffer = ""
        plain_input: list[str] = []
        index = 0
        mouse_prefix = "\033[<"

        while index < len(stream):
            if stream.startswith("\033[I", index) or stream.startswith("\033[O", index):
                if plain_input:
                    self.board.display.input("".join(plain_input))
                    plain_input = []
                self.handle_focus(stream[index + 2] == "I")
                index += 3
                continue

            if stream.startswith(mouse_prefix, index):
                if plain_input:
                    self.board.display.input("".join(plain_input))
                    plain_input = []
                end = index + len(mouse_prefix)
                while end < len(stream) and stream[end] not in "Mm":
                    end += 1
                if end >= len(stream):
                    self.input_sequence_buffer = stream[index:]
                    return
                sequence = stream[index : end + 1]
                if not self.handle_sgr_mouse_sequence(sequence):
                    self.board.display.input(sequence)
                index = end + 1
                continue

            remaining = stream[index:]
            if mouse_prefix.startswith(remaining):
                self.input_sequence_buffer = remaining
                break

            plain_input.append(stream[index])
            index += 1

        if plain_input:
            self.board.display.input("".join(plain_input))

    def flush_pending_input(self) -> None:
        """Release a held partial prefix that never became a mouse report.

        A lone ESC keypress matches the start of the mouse-report prefix, so
        handle_input buffers it; when no follow-up arrives within an input-loop
        tick it was a real ESC and must reach the child.
        """
        if self.input_sequence_buffer:
            pending, self.input_sequence_buffer = self.input_sequence_buffer, ""
            self.board.display.input(pending)

    def handle_resize(self) -> None:
        """Re-read the host size and resize the emulator (called from a SIGWINCH handler)."""
        size = shutil.get_terminal_size()
        self.width = size.columns
        self.height = size.lines - 2
        logger.info("Resize: %sx%s", self.width, self.height)
        self.board.resize(self.width, self.height)

    # --- run loop --- #

    async def input_loop(self) -> None:
        """Read host input and forward it."""

        def read_input():
            try:
                if self.is_windows and HAS_MSVCRT:
                    if msvcrt.kbhit():
                        char = msvcrt.getch()
                        return char.decode("utf-8", errors="replace") if isinstance(char, bytes) else char
                    return None
                readable, _, _ = select.select([sys.stdin.fileno()], [], [], 0)
                if not readable:
                    return None
                raw = os.read(sys.stdin.fileno(), 4096)
                return "" if raw == b"" else raw.decode("utf-8", errors="replace")
            except (OSError, BlockingIOError):
                return None

        while self.running:
            try:
                data = read_input()
                if data == "":
                    self.running = False
                    break
                if data:
                    self.handle_input(data)
                else:
                    self.flush_pending_input()
                await asyncio.sleep(0.01)
            except Exception:
                logger.exception("Error in input loop")
                break

    async def run(self) -> None:
        """Main loop: start the shell, pump input, render until it exits."""
        logger.info("Starting main loop")
        loop = asyncio.get_running_loop()
        if hasattr(signal, "SIGWINCH"):  # venue physics: the hosting tty reports resizes
            loop.add_signal_handler(signal.SIGWINCH, self.handle_resize)
        try:
            self.setup_terminal()
            self.probe_capabilities()
            self.board.set_pty_data_callback(self.handle_pty_data)
            await self.board.start_process()
            self.render_screen()

            input_task = asyncio.create_task(self.input_loop())
            while self.running:
                await asyncio.sleep(0.01)
                if self.dirty:
                    self.dirty = False
                    self.render_screen()
                if self.board.process and self.board.process.poll() is not None:
                    self.running = False
                    break
                if not self.board.process:
                    self.running = False
                    break

            if self.dirty:  # paint whatever arrived after the last tick
                self.render_screen()

            input_task.cancel()
            try:
                await input_task
            except asyncio.CancelledError:
                pass
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt")
        except Exception:
            logger.exception("Unhandled stdio terminal error")
            raise
        finally:
            if hasattr(signal, "SIGWINCH"):
                loop.remove_signal_handler(signal.SIGWINCH)
            self.cleanup()

    def cleanup(self) -> None:
        """Tear down the child and restore the host terminal."""
        logger.info("Cleaning up")
        self.running = False
        self.board.stop_process()
        self.restore_terminal()
