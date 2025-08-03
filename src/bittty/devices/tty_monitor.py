"""TTY Monitor device for host terminal output.

This device represents the physical TTY terminal we're writing to.
It handles writing to stdout, querying host terminal capabilities,
and properly rendering colors based on the host terminal's support.
"""

from __future__ import annotations

import os
import sys
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..command import Command

from .monitor import MonitorDevice
from ..tcaps import TermInfo
from ..style import Style

logger = logging.getLogger(__name__)


class TTYMonitorDevice(MonitorDevice):
    """Monitor device that represents the host TTY terminal.

    This device handles:
    - Writing ANSI sequences to sys.stdout
    - Querying host terminal capabilities via terminfo
    - Proper color and style rendering based on host terminal support
    - Terminal setup/cleanup (cursor visibility, screen clearing)
    """

    def __init__(self, width: int = 80, height: int = 24, board=None):
        """Initialize the TTY monitor device."""
        super().__init__(width, height, board)

        # Get terminal capabilities from terminfo
        self.term_name = os.environ.get("TERM", "xterm")
        try:
            self.terminfo = TermInfo(self.term_name, "")
        except Exception as e:
            logger.warning(f"Failed to load terminfo for {self.term_name}: {e}")
            self.terminfo = None

        # Host terminal capabilities
        self.supports_256_colors = self._check_256_color_support()
        self.supports_rgb_colors = self._check_rgb_color_support()
        self.supports_cursor_control = True  # Most terminals support this

        logger.debug(f"TTYMonitorDevice initialized for {self.term_name}")
        logger.debug(f"Capabilities: 256color={self.supports_256_colors}, RGB={self.supports_rgb_colors}")

    def get_command_handlers(self):
        """Return the commands this TTY monitor device handles."""
        handlers = super().get_command_handlers()
        handlers.update(
            {
                # TTY-specific commands
                "TTY_SETUP_SCREEN": self.handle_tty_setup_screen,
                "TTY_CLEANUP_SCREEN": self.handle_tty_cleanup_screen,
                "TTY_WRITE_OUTPUT": self.handle_tty_write_output,
            }
        )
        return handlers

    def query(self, feature_name: str) -> Any:
        """Query TTY monitor capabilities."""
        if feature_name == "terminal_name":
            return self.term_name
        elif feature_name == "colors":
            if self.supports_rgb_colors:
                return "rgb"
            elif self.supports_256_colors:
                return "256"
            else:
                return "16"
        elif feature_name == "256_colors":
            return self.supports_256_colors
        elif feature_name == "rgb_colors":
            return self.supports_rgb_colors
        elif feature_name == "cursor_control":
            return self.supports_cursor_control
        elif feature_name == "stdout_isatty":
            return sys.stdout.isatty()
        return super().query(feature_name)

    def _check_256_color_support(self) -> bool:
        """Check if the host terminal supports 256 colors."""
        # Check common indicators for 256 color support
        if "256color" in self.term_name:
            return True

        # Check terminfo capability if available
        if self.terminfo:
            try:
                colors = self.terminfo.get_number("colors")
                return colors >= 256
            except Exception:
                pass

        # Default to True for common terminals
        return self.term_name in ["xterm", "screen", "tmux"]

    def _check_rgb_color_support(self) -> bool:
        """Check if the host terminal supports RGB/truecolor."""
        # Check COLORTERM environment variable (modern standard)
        colorterm = os.environ.get("COLORTERM", "")
        if colorterm in ["truecolor", "24bit"]:
            return True

        # Check for terminals known to support RGB
        if any(term in self.term_name for term in ["xterm", "konsole", "gnome", "iterm"]):
            return True

        return False

    def setup_screen(self) -> None:
        """Set up the host terminal screen."""
        if not sys.stdout.isatty():
            return

        try:
            # Hide cursor and clear screen
            sys.stdout.write("\033[?25l\033[2J\033[H")
            sys.stdout.flush()
            logger.debug("Set up host terminal screen")
        except (OSError, UnicodeEncodeError) as e:
            logger.error(f"Failed to setup screen: {e}")

    def cleanup_screen(self) -> None:
        """Clean up the host terminal screen."""
        if not sys.stdout.isatty():
            return

        try:
            # Show cursor and clear screen
            sys.stdout.write("\033[?25h\033[2J\033[H")
            sys.stdout.flush()
            logger.debug("Cleaned up host terminal screen")
        except (OSError, UnicodeEncodeError) as e:
            logger.error(f"Failed to cleanup screen: {e}")

    def write_to_host_terminal(self, data: str) -> None:
        """Write data directly to the host terminal (stdout)."""
        if not sys.stdout.isatty():
            return

        try:
            sys.stdout.write(data)
            sys.stdout.flush()
        except (OSError, UnicodeEncodeError) as e:
            logger.error(f"Failed to write to host terminal: {e}")

    def render_screen_to_host(self) -> None:
        """Render the current screen buffer to the host terminal."""
        if not sys.stdout.isatty():
            return

        # Move to top-left corner
        self.write_to_host_terminal("\033[H")

        # Render each line of the screen buffer
        for y in range(self.height):
            line_content = ""
            current_style = None

            for x in range(self.width):
                cell = self.current_buffer.get_cell(x, y)
                if cell:
                    style, char = cell

                    # Apply style changes if needed
                    if style != current_style:
                        style_seq = self._style_to_ansi(style)
                        line_content += style_seq
                        current_style = style

                    line_content += char
                else:
                    line_content += " "

            # Reset style at end of line and clear to end of line
            line_content += "\033[0m\033[K"

            # Move to the line and write content
            self.write_to_host_terminal(f"\033[{y+1}H{line_content}")

    def _style_to_ansi(self, style: Any) -> str:
        """Convert a Style object to ANSI escape sequence.

        This properly handles the host terminal's color capabilities.
        """
        if isinstance(style, str):
            # If it's already an ANSI string, return as-is
            return style

        if not isinstance(style, Style):
            return ""

        # Build ANSI sequence based on style attributes
        ansi_parts = []

        # Reset if needed
        if style.is_reset:
            ansi_parts.append("0")

        # Text attributes
        if style.bold:
            ansi_parts.append("1")
        if style.dim:
            ansi_parts.append("2")
        if style.italic:
            ansi_parts.append("3")
        if style.underline:
            ansi_parts.append("4")
        if style.blink:
            ansi_parts.append("5")
        if style.reverse:
            ansi_parts.append("7")
        if style.strike:
            ansi_parts.append("9")

        # Colors - adapt to host terminal capabilities
        if style.fg_color:
            fg_code = self._color_to_ansi(style.fg_color, foreground=True)
            if fg_code:
                ansi_parts.append(fg_code)

        if style.bg_color:
            bg_code = self._color_to_ansi(style.bg_color, foreground=False)
            if bg_code:
                ansi_parts.append(bg_code)

        if ansi_parts:
            return f"\033[{';'.join(ansi_parts)}m"
        return ""

    def _color_to_ansi(self, color: Any, foreground: bool = True) -> str:
        """Convert a color to ANSI code based on host terminal capabilities."""
        if not color:
            return ""

        base = 30 if foreground else 40

        # Handle different color representations
        if isinstance(color, str):
            # Named colors
            color_map = {
                "black": base,
                "red": base + 1,
                "green": base + 2,
                "yellow": base + 3,
                "blue": base + 4,
                "magenta": base + 5,
                "cyan": base + 6,
                "white": base + 7,
            }
            return str(color_map.get(color.lower(), ""))

        elif isinstance(color, int):
            # 256-color mode
            if self.supports_256_colors and 0 <= color <= 255:
                return f"{base + 8};5;{color}"
            else:
                # Fallback to 16 colors
                return str(base + (color % 8))

        elif isinstance(color, tuple) and len(color) == 3:
            # RGB color
            if self.supports_rgb_colors:
                r, g, b = color
                return f"{base + 8};2;{r};{g};{b}"
            else:
                # Convert RGB to nearest 256 or 16 color
                # Simple conversion - could be improved
                return str(base + 7)  # Default to white/light gray

        return ""

    def handle_tty_setup_screen(self, command: "Command") -> None:
        """Handle TTY screen setup command."""
        self.setup_screen()
        return None

    def handle_tty_cleanup_screen(self, command: "Command") -> None:
        """Handle TTY screen cleanup command."""
        self.cleanup_screen()
        return None

    def handle_tty_write_output(self, command: "Command") -> None:
        """Handle writing output directly to TTY."""
        if command.args:
            self.write_to_host_terminal(command.args[0])
        return None

    def capture_pane_with_colors(self) -> str:
        """Capture the current screen with color information for display.

        This returns the screen content formatted for the host terminal.
        """
        lines = []
        for y in range(self.height):
            line = ""
            current_style = None

            for x in range(self.width):
                cell = self.current_buffer.get_cell(x, y)
                if cell:
                    style, char = cell

                    # Apply style changes if needed
                    if style != current_style:
                        style_seq = self._style_to_ansi(style)
                        line += style_seq
                        current_style = style

                    line += char
                else:
                    line += " "

            # Reset style at end of line
            line += "\033[0m"
            lines.append(line.rstrip())

        # Remove trailing empty lines
        while lines and not lines[-1].strip():
            lines.pop()

        return "\n".join(lines)

    def cleanup(self) -> None:
        """Clean up the TTY monitor device."""
        self.cleanup_screen()
