"""Monitor device for screen display functionality.

This device handles all screen-related operations including:
- Screen buffers (primary and alternate)
- Cursor positioning and movement
- Text rendering and character sets
- Colors and graphics attributes (SGR)
- Screen clearing and scrolling
- Scroll regions
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..command import Command

from ..device import Device
from ..buffer import Buffer
from ..charsets import get_charset

logger = logging.getLogger(__name__)


class MonitorDevice(Device):
    """A monitor device that handles screen display operations.

    This device emulates a CRT or LCD monitor that displays terminal content.
    It manages screen buffers, cursor position, text attributes, and all
    visual aspects of the terminal.
    """

    def __init__(self, width: int = 80, height: int = 24, board=None):
        """Initialize the monitor device.

        Args:
            width: Screen width in characters
            height: Screen height in characters
            board: Board to plug into
        """
        super().__init__(board)

        self.width = width
        self.height = height

        # Terminal state
        self.title = "Terminal"
        self.icon_title = "Terminal"
        self.cursor_x = 0
        self.cursor_y = 0
        self.cursor_visible = True

        # Terminal modes related to display
        self.auto_wrap = True
        self.insert_mode = False
        self.reverse_screen = False  # DECSCNM: False = normal, True = reverse video
        self.origin_mode = False  # DECOM: False = absolute, True = relative to scroll region

        # Screen buffers
        self.primary_buffer = Buffer(width, height)
        self.alt_buffer = Buffer(width, height)
        self.current_buffer = self.primary_buffer
        self.in_alt_screen = False

        # Scroll region (top, bottom) - 0-indexed
        self.scroll_top = 0
        self.scroll_bottom = height - 1

        # Current ANSI code for next write
        self.current_ansi_code: str = ""

        # Last printed character (for REP command)
        self.last_printed_char = " "

        # Character set state (G0-G3 sets)
        self.g0_charset = "B"  # Default: US ASCII
        self.g1_charset = "B"  # Default: US ASCII
        self.g2_charset = "B"  # Default: US ASCII
        self.g3_charset = "B"  # Default: US ASCII
        self.current_charset = 0  # 0 = G0, 1 = G1, 2 = G2, 3 = G3
        self.single_shift = None  # For SS2/SS3 (temporary shift)

        # Saved cursor state (for DECSC/DECRC)
        self.saved_cursor_x = 0
        self.saved_cursor_y = 0
        self.saved_ansi_code: str = ""

        logger.debug(f"MonitorDevice initialized: {width}x{height}")

    def get_command_handlers(self):
        """Return the commands this monitor device handles."""
        return {
            # Text output
            "TEXT": self.handle_text,
            # C0 controls
            "C0_BS": self.handle_backspace,
            "C0_HT": self.handle_tab,
            "C0_LF": self.handle_line_feed,
            "C0_CR": self.handle_carriage_return,
            "C0_SO": self.handle_shift_out,
            "C0_SI": self.handle_shift_in,
            "C0_DEL": self.handle_backspace,
            # CSI sequences - cursor movement
            "CSI_CUU": self.handle_cursor_up,  # ESC[A
            "CSI_CUD": self.handle_cursor_down,  # ESC[B
            "CSI_CUF": self.handle_cursor_forward,  # ESC[C
            "CSI_CUB": self.handle_cursor_back,  # ESC[D
            "CSI_CUP": self.handle_cursor_position,  # ESC[H
            "CSI_HVP": self.handle_cursor_position,  # ESC[f
            "CSI_VPA": self.handle_vertical_position_absolute,  # ESC[d
            "CSI_CHA": self.handle_cursor_horizontal_absolute,  # ESC[G
            # CSI sequences - screen control
            "CSI_ED": self.handle_erase_display,  # ESC[J
            "CSI_EL": self.handle_erase_line,  # ESC[K
            "CSI_DECSTBM": self.handle_set_scroll_region,  # ESC[r
            "CSI_SU": self.handle_scroll_up,  # ESC[S
            "CSI_SD": self.handle_scroll_down,  # ESC[T
            # CSI sequences - character attributes
            "CSI_SGR": self.handle_set_graphics_rendition,  # ESC[m
            # CSI sequences - editing
            "CSI_ICH": self.handle_insert_characters,  # ESC[@
            "CSI_DCH": self.handle_delete_characters,  # ESC[P
            "CSI_IL": self.handle_insert_lines,  # ESC[L
            "CSI_DL": self.handle_delete_lines,  # ESC[M
            "CSI_ECH": self.handle_erase_characters,  # ESC[X
            # CSI sequences - cursor save/restore
            "CSI_SCP": self.handle_save_cursor,  # ESC[s
            "CSI_RCP": self.handle_restore_cursor,  # ESC[u
            # CSI sequences - modes
            "CSI_SM": self.handle_set_mode,  # ESC[h
            "CSI_RM": self.handle_reset_mode,  # ESC[l
            "CSI_DECSET": self.handle_dec_set_mode,  # ESC[?h
            "CSI_DECRST": self.handle_dec_reset_mode,  # ESC[?l
            # ESC sequences
            "SAVE_CURSOR": self.handle_save_cursor_esc,  # ESC7
            "RESTORE_CURSOR": self.handle_restore_cursor_esc,  # ESC8
            "INDEX": self.handle_index,  # ESCD
            "REVERSE_INDEX": self.handle_reverse_index,  # ESCM
            "RESET_TERMINAL": self.handle_reset_terminal,  # ESCc
            # Character set commands
            "SET_G0_CHARSET": self.handle_set_g0_charset,
            "SET_G1_CHARSET": self.handle_set_g1_charset,
            "SET_G2_CHARSET": self.handle_set_g2_charset,
            "SET_G3_CHARSET": self.handle_set_g3_charset,
            "SINGLE_SHIFT_2": self.handle_single_shift_2,
            "SINGLE_SHIFT_3": self.handle_single_shift_3,
            # OSC sequences
            "OSC_0": self.handle_set_title,  # Set title and icon title
            "OSC_1": self.handle_set_icon_title,  # Set icon title
            "OSC_2": self.handle_set_title,  # Set title
        }

    def query(self, feature_name: str) -> Any:
        """Query monitor capabilities."""
        if feature_name == "screen_size":
            return (self.width, self.height)
        elif feature_name == "cursor_position":
            return (self.cursor_x, self.cursor_y)
        elif feature_name == "title":
            return self.title
        elif feature_name == "colors":
            return True  # Supports colors
        elif feature_name == "alternate_screen":
            return True
        return None

    def resize(self, width: int, height: int) -> None:
        """Resize the monitor."""
        self.width = width
        self.height = height
        self.primary_buffer.resize(width, height)
        self.alt_buffer.resize(width, height)
        self.scroll_bottom = height - 1

        # Keep cursor in bounds
        if self.cursor_x >= width:
            self.cursor_x = width - 1
        if self.cursor_y >= height:
            self.cursor_y = height - 1

    def get_content(self):
        """Get the current screen content."""
        return self.current_buffer.get_content()

    def capture_pane(self) -> str:
        """Capture the current screen as text."""
        lines = []
        for y in range(self.height):
            line = ""
            for x in range(self.width):
                cell = self.current_buffer.get_cell(x, y)
                if cell:
                    # cell is a tuple (Style, str)
                    line += cell[1]  # Get the character part
                else:
                    line += " "
            lines.append(line.rstrip())

        # Remove trailing empty lines
        while lines and not lines[-1]:
            lines.pop()

        return "\n".join(lines)

    # Command handlers

    def handle_text(self, command: "Command") -> None:
        """Handle text output."""
        if command.args:
            text = command.args[0]
            self.write_text(text, self.current_ansi_code)
        return None

    def handle_backspace(self, command: "Command") -> None:
        """Handle backspace."""
        self.backspace()
        return None

    def handle_tab(self, command: "Command") -> None:
        """Handle horizontal tab."""
        # Move to next tab stop (every 8 characters)
        self.cursor_x = ((self.cursor_x // 8) + 1) * 8
        if self.cursor_x >= self.width:
            self.cursor_x = self.width - 1
        return None

    def handle_line_feed(self, command: "Command") -> None:
        """Handle line feed."""
        self.line_feed()
        return None

    def handle_carriage_return(self, command: "Command") -> None:
        """Handle carriage return."""
        self.carriage_return()
        return None

    def handle_shift_out(self, command: "Command") -> None:
        """Handle shift out (SO)."""
        self.shift_out()
        return None

    def handle_shift_in(self, command: "Command") -> None:
        """Handle shift in (SI)."""
        self.shift_in()
        return None

    def handle_cursor_up(self, command: "Command") -> None:
        """Handle cursor up."""
        count = int(command.args[0]) if command.args else 1
        self.cursor_y = max(self.scroll_top if self.origin_mode else 0, self.cursor_y - count)
        return None

    def handle_cursor_down(self, command: "Command") -> None:
        """Handle cursor down."""
        count = int(command.args[0]) if command.args else 1
        max_y = self.scroll_bottom if self.origin_mode else self.height - 1
        self.cursor_y = min(max_y, self.cursor_y + count)
        return None

    def handle_cursor_forward(self, command: "Command") -> None:
        """Handle cursor forward."""
        count = int(command.args[0]) if command.args else 1
        self.cursor_x = min(self.width - 1, self.cursor_x + count)
        return None

    def handle_cursor_back(self, command: "Command") -> None:
        """Handle cursor back."""
        count = int(command.args[0]) if command.args else 1
        self.cursor_x = max(0, self.cursor_x - count)
        return None

    def handle_cursor_position(self, command: "Command") -> None:
        """Handle cursor position."""
        row = int(command.args[0]) if command.args else 1
        col = int(command.args[1]) if len(command.args) > 1 else 1

        # Convert to 0-based coordinates
        row -= 1
        col -= 1

        # Apply origin mode
        if self.origin_mode:
            row += self.scroll_top
            row = max(self.scroll_top, min(self.scroll_bottom, row))
        else:
            row = max(0, min(self.height - 1, row))

        col = max(0, min(self.width - 1, col))

        self.cursor_x = col
        self.cursor_y = row
        return None

    def handle_vertical_position_absolute(self, command: "Command") -> None:
        """Handle vertical position absolute."""
        row = int(command.args[0]) if command.args else 1
        row -= 1  # Convert to 0-based

        if self.origin_mode:
            row += self.scroll_top
            row = max(self.scroll_top, min(self.scroll_bottom, row))
        else:
            row = max(0, min(self.height - 1, row))

        self.cursor_y = row
        return None

    def handle_cursor_horizontal_absolute(self, command: "Command") -> None:
        """Handle cursor horizontal absolute."""
        col = int(command.args[0]) if command.args else 1
        col -= 1  # Convert to 0-based
        col = max(0, min(self.width - 1, col))
        self.cursor_x = col
        return None

    def handle_erase_display(self, command: "Command") -> None:
        """Handle erase display."""
        param = int(command.args[0]) if command.args else 0

        if param == 0:  # Clear from cursor to end of screen
            # Clear from cursor to end of current line
            self.current_buffer.clear_line(self.cursor_y, self.cursor_x, self.width)
            # Clear all lines below cursor
            for y in range(self.cursor_y + 1, self.height):
                self.current_buffer.clear_line(y)
        elif param == 1:  # Clear from beginning of screen to cursor
            # Clear all lines above cursor
            for y in range(0, self.cursor_y):
                self.current_buffer.clear_line(y)
            # Clear from beginning of current line to cursor
            self.current_buffer.clear_line(self.cursor_y, 0, self.cursor_x + 1)
        elif param == 2:  # Clear entire screen
            self.current_buffer.clear_region(0, 0, self.width - 1, self.height - 1)
        elif param == 3:  # Clear entire screen and scrollback
            self.current_buffer.clear_region(0, 0, self.width - 1, self.height - 1)
            # TODO: Clear scrollback when implemented

        return None

    def handle_erase_line(self, command: "Command") -> None:
        """Handle erase line."""
        param = int(command.args[0]) if command.args else 0

        if param == 0:  # Clear from cursor to end of line
            self.current_buffer.clear_line(self.cursor_y, self.cursor_x, self.width)
        elif param == 1:  # Clear from beginning of line to cursor
            self.current_buffer.clear_line(self.cursor_y, 0, self.cursor_x + 1)
        elif param == 2:  # Clear entire line
            self.current_buffer.clear_line(self.cursor_y)

        return None

    def handle_set_scroll_region(self, command: "Command") -> None:
        """Handle set scroll region."""
        top = int(command.args[0]) if command.args else 1
        bottom = int(command.args[1]) if len(command.args) > 1 else self.height

        # Convert to 0-based and validate
        top = max(1, min(self.height, top)) - 1
        bottom = max(1, min(self.height, bottom)) - 1

        if top < bottom:
            self.scroll_top = top
            self.scroll_bottom = bottom

            # Move cursor to home position
            if self.origin_mode:
                self.cursor_x = 0
                self.cursor_y = self.scroll_top
            else:
                self.cursor_x = 0
                self.cursor_y = 0

        return None

    def handle_scroll_up(self, command: "Command") -> None:
        """Handle scroll up."""
        count = int(command.args[0]) if command.args else 1
        self.scroll(-count)  # Negative for up
        return None

    def handle_scroll_down(self, command: "Command") -> None:
        """Handle scroll down."""
        count = int(command.args[0]) if command.args else 1
        self.scroll(count)
        return None

    def handle_set_graphics_rendition(self, command: "Command") -> None:
        """Handle SGR (Select Graphics Rendition)."""
        # Update current ANSI code based on SGR parameters
        params = command.args if command.args else (0,)

        # Build ANSI sequence for this SGR command
        param_str = ";".join(str(p) for p in params)
        self.current_ansi_code = f"\x1b[{param_str}m"

        return None

    def handle_insert_characters(self, command: "Command") -> None:
        """Handle insert characters."""
        count = int(command.args[0]) if command.args else 1
        self.insert_characters(count, self.current_ansi_code)
        return None

    def handle_delete_characters(self, command: "Command") -> None:
        """Handle delete characters."""
        count = int(command.args[0]) if command.args else 1
        self.delete_characters(count)
        return None

    def handle_insert_lines(self, command: "Command") -> None:
        """Handle insert lines."""
        count = int(command.args[0]) if command.args else 1
        self.insert_lines(count)
        return None

    def handle_delete_lines(self, command: "Command") -> None:
        """Handle delete lines."""
        count = int(command.args[0]) if command.args else 1
        self.delete_lines(count)
        return None

    def handle_erase_characters(self, command: "Command") -> None:
        """Handle erase characters."""
        count = int(command.args[0]) if command.args else 1
        for i in range(count):
            if self.cursor_x + i < self.width:
                self.current_buffer.set_cell(self.cursor_x + i, self.cursor_y, " ", "")
        return None

    def handle_save_cursor(self, command: "Command") -> None:
        """Handle save cursor position (CSI)."""
        self.save_cursor()
        return None

    def handle_restore_cursor(self, command: "Command") -> None:
        """Handle restore cursor position (CSI)."""
        self.restore_cursor()
        return None

    def handle_save_cursor_esc(self, command: "Command") -> None:
        """Handle save cursor position (ESC)."""
        self.save_cursor()
        return None

    def handle_restore_cursor_esc(self, command: "Command") -> None:
        """Handle restore cursor position (ESC)."""
        self.restore_cursor()
        return None

    def handle_index(self, command: "Command") -> None:
        """Handle index (move down and scroll if needed)."""
        if self.cursor_y >= self.scroll_bottom:
            self.scroll(1)
        else:
            self.cursor_y += 1
        return None

    def handle_reverse_index(self, command: "Command") -> None:
        """Handle reverse index (move up and scroll if needed)."""
        if self.cursor_y <= self.scroll_top:
            self.scroll(-1)
        else:
            self.cursor_y -= 1
        return None

    def handle_reset_terminal(self, command: "Command") -> None:
        """Handle terminal reset."""
        # Reset to initial state
        self.cursor_x = 0
        self.cursor_y = 0
        self.cursor_visible = True
        self.current_ansi_code = ""
        self.current_buffer.clear()
        # Reset modes and other state...
        return None

    def handle_set_mode(self, command: "Command") -> None:
        """Handle set mode."""
        for arg in command.args:
            mode = int(arg)
            self.set_mode(mode, False)
        return None

    def handle_reset_mode(self, command: "Command") -> None:
        """Handle reset mode."""
        for arg in command.args:
            mode = int(arg)
            self.clear_mode(mode, False)
        return None

    def handle_dec_set_mode(self, command: "Command") -> None:
        """Handle DEC private set mode."""
        for arg in command.args:
            mode = int(arg)
            self.set_mode(mode, True)
        return None

    def handle_dec_reset_mode(self, command: "Command") -> None:
        """Handle DEC private reset mode."""
        for arg in command.args:
            mode = int(arg)
            self.clear_mode(mode, True)
        return None

    def handle_set_g0_charset(self, command: "Command") -> None:
        """Handle set G0 character set."""
        if command.args:
            self.set_g0_charset(command.args[0])
        return None

    def handle_set_g1_charset(self, command: "Command") -> None:
        """Handle set G1 character set."""
        if command.args:
            self.set_g1_charset(command.args[0])
        return None

    def handle_set_g2_charset(self, command: "Command") -> None:
        """Handle set G2 character set."""
        if command.args:
            self.set_g2_charset(command.args[0])
        return None

    def handle_set_g3_charset(self, command: "Command") -> None:
        """Handle set G3 character set."""
        if command.args:
            self.set_g3_charset(command.args[0])
        return None

    def handle_single_shift_2(self, command: "Command") -> None:
        """Handle single shift 2."""
        self.single_shift_2()
        return None

    def handle_single_shift_3(self, command: "Command") -> None:
        """Handle single shift 3."""
        self.single_shift_3()
        return None

    def handle_set_title(self, command: "Command") -> None:
        """Handle set title."""
        if len(command.args) >= 2:
            title = command.args[1]
            self.set_title(title)
        return None

    def handle_set_icon_title(self, command: "Command") -> None:
        """Handle set icon title."""
        if len(command.args) >= 2:
            icon_title = command.args[1]
            self.set_icon_title(icon_title)
        return None

    # Implementation methods (extracted from Terminal class)

    def write_text(self, text: str, ansi_code: str = "") -> None:
        """Write text to the current buffer."""
        for char in text:
            # Translate character through current charset
            translated_char = self._translate_charset(char)

            # Handle wrapping
            if self.cursor_x >= self.width:
                if self.auto_wrap:
                    self.cursor_x = 0
                    self.line_feed(is_wrapped=True)
                else:
                    self.cursor_x = self.width - 1

            # Insert mode
            if self.insert_mode:
                self.current_buffer.insert_character(self.cursor_x, self.cursor_y, translated_char, ansi_code)
            else:
                self.current_buffer.set_cell(self.cursor_x, self.cursor_y, translated_char, ansi_code)

            self.cursor_x += 1
            self.last_printed_char = char

    def _translate_charset(self, text: str) -> str:
        """Translate text through the current character set."""
        charset_name = [self.g0_charset, self.g1_charset, self.g2_charset, self.g3_charset][self.current_charset]

        # Handle single shift override
        if self.single_shift is not None:
            charset_name = [self.g0_charset, self.g1_charset, self.g2_charset, self.g3_charset][self.single_shift]
            self.single_shift = None  # Reset after use

        charset = get_charset(charset_name)
        if charset:
            return charset.get(text, text)
        return text

    def set_g0_charset(self, charset: str) -> None:
        """Set G0 character set."""
        self.g0_charset = charset

    def set_g1_charset(self, charset: str) -> None:
        """Set G1 character set."""
        self.g1_charset = charset

    def set_g2_charset(self, charset: str) -> None:
        """Set G2 character set."""
        self.g2_charset = charset

    def set_g3_charset(self, charset: str) -> None:
        """Set G3 character set."""
        self.g3_charset = charset

    def shift_in(self) -> None:
        """Shift In - use G0 character set."""
        self.current_charset = 0

    def shift_out(self) -> None:
        """Shift Out - use G1 character set."""
        self.current_charset = 1

    def single_shift_2(self) -> None:
        """Single Shift 2 - use G2 for next character only."""
        self.single_shift = 2

    def single_shift_3(self) -> None:
        """Single Shift 3 - use G3 for next character only."""
        self.single_shift = 3

    def line_feed(self, is_wrapped: bool = False) -> None:
        """Move cursor down one line, scrolling if necessary."""
        if self.cursor_y >= self.scroll_bottom:
            self.scroll(1)
        else:
            self.cursor_y += 1

    def carriage_return(self) -> None:
        """Move cursor to beginning of current line."""
        self.cursor_x = 0

    def backspace(self) -> None:
        """Move cursor back one position."""
        if self.cursor_x > 0:
            self.cursor_x -= 1

    def set_mode(self, mode: int, private: bool = False) -> None:
        """Set a terminal mode."""
        if private:
            # DEC private modes
            if mode == 1:  # DECCKM - Cursor Keys Mode
                self.cursor_application_mode = True
            elif mode == 3:  # DECCOLM - 132 Column Mode
                pass  # Would resize to 132 columns
            elif mode == 6:  # DECOM - Origin Mode
                self.origin_mode = True
                self.cursor_x = 0
                self.cursor_y = self.scroll_top
            elif mode == 7:  # DECAWM - Auto Wrap Mode
                self.auto_wrap = True
            elif mode == 25:  # DECTCEM - Text Cursor Enable Mode
                self.cursor_visible = True
            elif mode == 1047:  # Alternate Screen Buffer
                self.switch_screen(True)
            elif mode == 1049:  # Save cursor and switch to alternate screen
                self.save_cursor()
                self.switch_screen(True)
        else:
            # ANSI modes
            if mode == 4:  # IRM - Insert/Replace Mode
                self.insert_mode = True
            elif mode == 20:  # LNM - Line Feed/New Line Mode
                pass  # Would affect LF behavior

    def clear_mode(self, mode: int, private: bool = False) -> None:
        """Clear a terminal mode."""
        if private:
            # DEC private modes
            if mode == 1:  # DECCKM
                self.cursor_application_mode = False
            elif mode == 6:  # DECOM
                self.origin_mode = False
                self.cursor_x = 0
                self.cursor_y = 0
            elif mode == 7:  # DECAWM
                self.auto_wrap = False
            elif mode == 25:  # DECTCEM
                self.cursor_visible = False
            elif mode == 1047:  # Alternate Screen Buffer
                self.switch_screen(False)
            elif mode == 1049:  # Restore cursor and switch to normal screen
                self.switch_screen(False)
                self.restore_cursor()
        else:
            # ANSI modes
            if mode == 4:  # IRM
                self.insert_mode = False

    def switch_screen(self, alt: bool) -> None:
        """Switch between primary and alternate screen buffers."""
        if alt and not self.in_alt_screen:
            self.current_buffer = self.alt_buffer
            self.in_alt_screen = True
        elif not alt and self.in_alt_screen:
            self.current_buffer = self.primary_buffer
            self.in_alt_screen = False

    def set_title(self, title: str) -> None:
        """Set the terminal title."""
        self.title = title

    def set_icon_title(self, icon_title: str) -> None:
        """Set the terminal icon title."""
        self.icon_title = icon_title

    def save_cursor(self) -> None:
        """Save current cursor position and attributes."""
        self.saved_cursor_x = self.cursor_x
        self.saved_cursor_y = self.cursor_y
        self.saved_ansi_code = self.current_ansi_code

    def restore_cursor(self) -> None:
        """Restore saved cursor position and attributes."""
        self.cursor_x = self.saved_cursor_x
        self.cursor_y = self.saved_cursor_y
        self.current_ansi_code = self.saved_ansi_code

    def insert_lines(self, count: int) -> None:
        """Insert lines at cursor position."""
        if self.cursor_y >= self.scroll_top and self.cursor_y <= self.scroll_bottom:
            for _ in range(count):
                self.current_buffer.insert_line(self.cursor_y)
                # Remove line at bottom of scroll region
                if self.scroll_bottom < self.height - 1:
                    self.current_buffer.delete_line(self.scroll_bottom)

    def delete_lines(self, count: int) -> None:
        """Delete lines at cursor position."""
        if self.cursor_y >= self.scroll_top and self.cursor_y <= self.scroll_bottom:
            for _ in range(count):
                self.current_buffer.delete_line(self.cursor_y)
                # Add blank line at bottom of scroll region
                if self.scroll_bottom < self.height - 1:
                    self.current_buffer.insert_line(self.scroll_bottom)

    def insert_characters(self, count: int, ansi_code: str = "") -> None:
        """Insert characters at cursor position."""
        for _ in range(count):
            self.current_buffer.insert_character(self.cursor_x, self.cursor_y, " ", ansi_code)

    def delete_characters(self, count: int) -> None:
        """Delete characters at cursor position."""
        for _ in range(count):
            self.current_buffer.delete_character(self.cursor_x, self.cursor_y)

    def scroll(self, lines: int) -> None:
        """Scroll the screen or scroll region."""
        if lines > 0:
            # Scroll down (content moves up)
            for _ in range(lines):
                # Move lines up within scroll region
                for y in range(self.scroll_top, self.scroll_bottom):
                    for x in range(self.width):
                        cell = self.current_buffer.get_cell(x, y + 1)
                        if cell:
                            # cell is a tuple (Style, str)
                            self.current_buffer.set_cell(x, y, cell[1], cell[0])
                        else:
                            self.current_buffer.set_cell(x, y, " ", "")

                # Clear bottom line of scroll region
                for x in range(self.width):
                    self.current_buffer.set_cell(x, self.scroll_bottom, " ", "")

        elif lines < 0:
            # Scroll up (content moves down)
            for _ in range(-lines):
                # Move lines down within scroll region
                for y in range(self.scroll_bottom, self.scroll_top, -1):
                    for x in range(self.width):
                        cell = self.current_buffer.get_cell(x, y - 1)
                        if cell:
                            # cell is a tuple (Style, str)
                            self.current_buffer.set_cell(x, y, cell[1], cell[0])
                        else:
                            self.current_buffer.set_cell(x, y, " ", "")

                # Clear top line of scroll region
                for x in range(self.width):
                    self.current_buffer.set_cell(x, self.scroll_top, " ", "")
