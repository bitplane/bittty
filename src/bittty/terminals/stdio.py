"""StdioTerminal: the reference terminal, whose venue is this process's stdio.

Composes a Board (never subclasses it) and drives the real outer terminal:
raw-mode stdin, ANSI rendering to stdout, resize handling, and mouse and Unicode-policy
mirroring. Discrete side-effects arrive through the Terminal hooks.
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
from .keyboard_input import KeyboardInput
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
    """Render a bittty Board to the real terminal this program is running in.

    Uses the whole venue. A subclass that wants chrome of its own — a status
    bar, a border — sets ``reserved_rows`` to keep rows off the emulated screen
    and overrides ``draw_chrome()`` to paint them.
    """

    # Rows at the bottom of the venue that are the terminal's own, not the board's.
    reserved_rows = 0

    def __init__(self) -> None:
        size = shutil.get_terminal_size()
        self.width = size.columns
        self.height = size.lines - self.reserved_rows
        self.is_windows = platform.system() == "Windows"
        board = Board(command=self.get_default_shell(), width=self.width, height=self.height)
        super().__init__(board)
        self.attach()

        self.running = True
        self.old_termios = None
        self.host_mouse_mode: str | None = None
        self.initial_ambiguous_width: int | None = None
        self.host_ambiguous_width: int | None = None
        self.host_grapheme_mutable = False
        self.initial_grapheme_clustering: bool | None = None
        self.host_grapheme_clustering: bool | None = None
        self.host_keyboard_flags: int | None = None
        self.host_keyboard_pushed = False
        self.startup_input = b""
        self.input_parser = KeyboardInput(self)
        self.dirty = False  # PTY data arrived; the run loop repaints on its tick
        self._seen_page = None  # video page rendered last frame
        self._seen_gen = -1  # its generation when we rendered it

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

    def on_reverse_screen(self, enabled: bool) -> None:
        """Mirror the child's normal/reverse screen selection."""
        print(f"\033[?5{'h' if enabled else 'l'}", end="", flush=True)

    def on_cursor_blink(self, enabled: bool) -> None:
        """Mirror the child's cursor-blink selection."""
        print(f"\033[?12{'h' if enabled else 'l'}", end="", flush=True)

    def on_keyboard_indicator(self, num_lock: bool, caps_lock: bool, scroll_lock: bool) -> None:
        """Mirror the keyboard LEDs onto the outer terminal via DECLL."""
        lit = "".join(f"\033[{n}q" for n, on in ((1, num_lock), (2, caps_lock), (3, scroll_lock)) if on)
        print(f"\033[0q{lit}", end="", flush=True)

    def on_ambiguous_width(self, width: int) -> None:
        """Mirror the child's ambiguous-width policy onto the outer terminal."""
        if width == self.host_ambiguous_width:
            return
        suffix = "h" if width == 2 else "l"
        print(f"\033[?8840{suffix}", end="", flush=True)
        self.host_ambiguous_width = width

    def on_grapheme_clustering(self, enabled: bool) -> None:
        """Mirror mutable Unicode Core mode onto the outer terminal."""
        if not self.host_grapheme_mutable or enabled == self.host_grapheme_clustering:
            return
        suffix = "h" if enabled else "l"
        print(f"\033[?2027{suffix}", end="", flush=True)
        self.host_grapheme_clustering = enabled

    def on_mouse_capture(self, mode: str) -> None:
        """Capture the physical mouse events requested by the board."""
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
        print("\033[?5;12;2004s\033[?2004h\033[?5l\033[?12l\033[?25l\033[?1004h\033[2J\033[H", end="", flush=True)

    def restore_terminal(self) -> None:
        """Restore the host terminal to its original state."""
        logger.info("Restoring terminal")
        if self.host_keyboard_pushed:
            print("\033[<u", end="", flush=True)
            self.host_keyboard_pushed = False
        self.host_keyboard_flags = None
        self.disable_host_mouse()
        self.on_ambiguous_width(self.initial_ambiguous_width or 1)
        if self.initial_grapheme_clustering is not None:
            self.on_grapheme_clustering(self.initial_grapheme_clustering)
        if HAS_UNIX_TERMIOS and self.old_termios:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.old_termios)
        # 0q: DECLL has no save/restore analogue, so extinguish the LEDs rather
        # than leak the child's indications onto the outer terminal.
        print("\033[?1004l\033[?25h\033[2J\033[H\033[?5;12;2004r\033[0q", end="", flush=True)

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
        pending_input = []
        caps = probe_caps(fd, write, os.environ, on_input=pending_input.append)
        if caps.kitty_keyboard_flags is not None:
            self.host_keyboard_flags = caps.kitty_keyboard_flags
            # Own one stack entry on the outer terminal's current screen.
            # Child screen changes are rendered, not mirrored as screen switches.
            self.host_keyboard_pushed = True
            write("\033[>31u\033[?u")
        self.startup_input = b"".join(pending_input)
        self.initial_ambiguous_width = caps.ambiguous_width
        self.host_ambiguous_width = caps.ambiguous_width
        self.host_grapheme_mutable = caps.grapheme_mode in ("set", "reset")
        if caps.grapheme_mode in ("set", "reset"):
            self.initial_grapheme_clustering = caps.grapheme_mode == "set"
            self.host_grapheme_clustering = self.initial_grapheme_clustering
        else:
            self.initial_grapheme_clustering = None
            self.host_grapheme_clustering = None
        # This may synchronously emit GraphemeClusteringChanged back through
        # the display seam, so host state must be recorded first.
        self.set_caps(caps)
        logger.info("Display caps: %s", caps)

    def render_screen(self) -> None:
        """Render the current board state to stdout, then place the host's hardware cursor.

        The cursor is the host terminal's own: position it and show it when the
        child wants it visible (DECTCEM). The host hollows it on unfocus by
        itself, exactly like a real terminal.
        """
        page = self.board.blitter.current_page
        if page is self._seen_page:
            rows = page.dirty_rows(self._seen_gen)
        else:
            rows = range(page.height)  # new page (startup or alt-screen flip): paint everything
        self._seen_page = page
        self._seen_gen = page.observe()

        print("\033[?25l", end="")
        for y in rows:
            if y < self.height:
                print(f"\033[{y + 1}H{page.get_line(y, width=self.width)}\033[K", end="")
        self.draw_chrome()
        board = self.board
        if board.modes.cursor_visible and board.cursor.y < self.height:
            print(f"\033[{board.cursor.y + 1};{board.cursor.display_x + 1}H\033[?25h", end="", flush=True)
        else:
            print(end="", flush=True)

    def draw_chrome(self) -> None:
        """Paint the terminal's own rows, if it reserved any.

        Called after the board's rows and before the hardware cursor is placed,
        so a subclass can leave the cursor where the child put it.
        """

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

    def handle_input(self, data: str | bytes) -> None:
        """Decode outer input into keyboard, text, paste, mouse and focus events."""
        self.input_parser.feed(data)

    def flush_pending_input(self) -> None:
        """Resolve a legacy lone Escape on idle; explicit reports stay pending."""
        self.input_parser.flush_trailing()

    def handle_resize(self) -> None:
        """Re-read the host size and resize the emulator (called from a SIGWINCH handler)."""
        size = shutil.get_terminal_size()
        self.width = size.columns
        self.height = size.lines - self.reserved_rows
        logger.info("Resize: %sx%s", self.width, self.height)
        self.board.display.resize(self.width, self.height)

    # --- run loop --- #

    async def input_loop(self) -> None:
        """Read host input and forward it."""

        def read_input():
            try:
                if self.is_windows and HAS_MSVCRT:
                    if msvcrt.kbhit():
                        char = msvcrt.getch()
                        return char
                    return None
                readable, _, _ = select.select([sys.stdin.fileno()], [], [], 0)
                if not readable:
                    return None
                raw = os.read(sys.stdin.fileno(), 4096)
                return "" if raw == b"" else raw
            except (OSError, BlockingIOError):
                return None

        while self.running:
            try:
                data = read_input()
                if data == "":
                    self.input_parser.finish()
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
            self.handle_input(self.startup_input)
            self.startup_input = b""
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
