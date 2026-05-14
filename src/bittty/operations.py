"""Parser operations and default terminal operation sink."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from . import constants

if TYPE_CHECKING:
    from .terminal import Terminal

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Operation:
    """A parsed terminal operation."""

    kind: str
    name: str
    args: tuple[Any, ...] = field(default_factory=tuple)
    raw: str = ""


class OperationSink(Protocol):
    """Receives operations emitted by the parser."""

    def handle_operation(self, operation: Operation) -> None:
        """Handle one parsed operation."""


CONTROL_NAMES = {
    constants.BEL: "C0_BEL",
    constants.BS: "C0_BS",
    constants.HT: "C0_HT",
    constants.LF: "C0_LF",
    constants.VT: "C0_VT",
    constants.FF: "C0_FF",
    constants.CR: "C0_CR",
    constants.SO: "C0_SO",
    constants.SI: "C0_SI",
    constants.DEL: "C0_DEL",
}


def control_name(ch: str) -> str:
    """Return a stable operation name for a C0 control character."""
    return CONTROL_NAMES.get(ch, f"C0_{ord(ch):02X}")


class TerminalOperationSink:
    """Applies parser operations to the current Terminal implementation."""

    def __init__(self, terminal: Terminal) -> None:
        self.terminal = terminal

    def handle_operation(self, operation: Operation) -> None:
        if operation.kind == "text" and operation.name == "PRINT":
            self.terminal.write_text(operation.args[0], self.terminal.current_ansi_code)
            return

        if operation.kind == "control":
            self._handle_control(operation)
            return

        if operation.kind == "escape":
            self._handle_escape(operation)
            return

        if operation.kind == "charset":
            self._handle_charset(operation)
            return

        if operation.kind == "cursor":
            self._handle_cursor(operation)
            return

        if operation.kind == "edit":
            self._handle_edit(operation)
            return

        if operation.kind == "screen":
            self._handle_screen(operation)
            return

        if operation.kind == "style":
            self._handle_style(operation)
            return

        if operation.kind == "query":
            self._handle_query(operation)
            return

        if operation.kind == "title":
            self._handle_title(operation)
            return

        if operation.kind == "mode":
            self._handle_mode(operation)
            return

        if operation.kind in ("csi", "osc", "dcs"):
            logger.debug("%s: %r", operation.name, operation.raw)
            return

        if operation.kind in ("apc", "pm", "sos"):
            logger.debug("%s: %r", operation.name, operation.raw)
            return

        logger.debug("Unknown operation: %s", operation)

    def _handle_control(self, operation: Operation) -> None:
        ch = operation.raw
        if ch == constants.BEL:
            self.terminal.bell()
        elif ch == constants.BS:
            self.terminal.backspace()
        elif ch == constants.HT:
            self.terminal.cursor_x = self.terminal.next_tab_stop()
        elif ch in (constants.LF, constants.VT, constants.FF):
            self.terminal.line_feed()
        elif ch == constants.CR:
            self.terminal.cursor_x = 0
        elif ch == constants.SO:
            self.terminal.current_charset = 1
        elif ch == constants.SI:
            self.terminal.current_charset = 0
        elif ch == constants.DEL:
            pass
        elif operation.name == "IND":
            self.terminal.line_feed()
        elif operation.name == "RI":
            if self.terminal.cursor_y <= self.terminal.scroll_top:
                self.terminal.scroll(-1)
            else:
                self.terminal.cursor_y -= 1
        elif operation.name == "ST":
            pass
        elif operation.name == "NEL":
            self.terminal.cursor_x = 0
            self.terminal.line_feed()
        elif operation.name == "HTS":
            self.terminal.set_tab_stop(self.terminal.cursor_x)

    def _handle_escape(self, operation: Operation) -> None:
        if operation.name == "SS2":
            self.terminal.single_shift_2()
            return
        if operation.name == "SS3":
            self.terminal.single_shift_3()
            return

        logger.debug("Unknown escape operation: %s", operation)

    def _handle_charset(self, operation: Operation) -> None:
        (charset,) = operation.args
        if operation.name == "SCS_G0":
            self.terminal.set_g0_charset(charset)
            return
        if operation.name == "SCS_G1":
            self.terminal.set_g1_charset(charset)
            return
        if operation.name == "SCS_G2":
            self.terminal.set_g2_charset(charset)
            return
        if operation.name == "SCS_G3":
            self.terminal.set_g3_charset(charset)
            return

        logger.debug("Unknown charset operation: %s", operation)

    def _handle_cursor(self, operation: Operation) -> None:
        if operation.name in ("CUP", "HVP"):
            col, row = operation.args
            self.terminal.set_cursor(col, row)
            return
        if operation.name == "CUU":
            (count,) = operation.args
            self.terminal.cursor_y = max(0, self.terminal.cursor_y - count)
            return
        if operation.name == "CUD":
            (count,) = operation.args
            self.terminal.cursor_y = min(self.terminal.height - 1, self.terminal.cursor_y + count)
            return
        if operation.name == "CUF":
            (count,) = operation.args
            self.terminal.cursor_x = min(self.terminal.width - 1, self.terminal.cursor_x + count)
            return
        if operation.name == "CUB":
            (count,) = operation.args
            self.terminal.cursor_x = max(0, self.terminal.cursor_x - count)
            return
        if operation.name == "CHA":
            (col,) = operation.args
            self.terminal.set_cursor(col, None)
            return
        if operation.name == "VPA":
            (row,) = operation.args
            self.terminal.set_cursor(None, row)
            return
        if operation.name == "SAVE":
            self.terminal.save_cursor()
            return
        if operation.name == "RESTORE":
            self.terminal.restore_cursor()
            return

        logger.debug("Unknown cursor operation: %s", operation)

    def _handle_edit(self, operation: Operation) -> None:
        if operation.name == "ED":
            (mode,) = operation.args
            self.terminal.clear_screen(mode)
            return
        if operation.name == "EL":
            (mode,) = operation.args
            self.terminal.clear_line(mode)
            return
        if operation.name == "IL":
            (count,) = operation.args
            self.terminal.insert_lines(count)
            return
        if operation.name == "DL":
            (count,) = operation.args
            self.terminal.delete_lines(count)
            return
        if operation.name == "ICH":
            (count,) = operation.args
            self.terminal.insert_characters(count, self.terminal.current_ansi_code)
            return
        if operation.name == "DCH":
            (count,) = operation.args
            self.terminal.delete_characters(count)
            return
        if operation.name == "ECH":
            (count,) = operation.args
            for _ in range(count):
                self.terminal.current_buffer.set(
                    self.terminal.cursor_x,
                    self.terminal.cursor_y,
                    " ",
                    self.terminal.current_ansi_code,
                )
                if self.terminal.cursor_x < self.terminal.width - 1:
                    self.terminal.cursor_x += 1
            return
        if operation.name == "SU":
            (count,) = operation.args
            self.terminal.scroll(count)
            return
        if operation.name == "SD":
            (count,) = operation.args
            self.terminal.scroll(-count)
            return
        if operation.name == "REP":
            (count,) = operation.args
            self.terminal.repeat_last_character(count)
            return

        logger.debug("Unknown edit operation: %s", operation)

    def _handle_screen(self, operation: Operation) -> None:
        if operation.name == "DECSTBM":
            top, bottom = operation.args
            self.terminal.set_scroll_region(top, self.terminal.height - 1 if bottom is None else bottom)
            return
        if operation.name == "RIS":
            self.terminal.clear_screen(constants.ERASE_ALL)
            self.terminal.set_cursor(0, 0)
            self.terminal.current_ansi_code = ""
            self.terminal.set_g0_charset("B")
            self.terminal.set_g1_charset("B")
            self.terminal.set_g2_charset("B")
            self.terminal.set_g3_charset("B")
            self.terminal.current_charset = 0
            self.terminal.single_shift = None
            return

        logger.debug("Unknown screen operation: %s", operation)

    def _handle_style(self, operation: Operation) -> None:
        if operation.name == "SGR":
            from .style import Style, parse_sgr_sequence, style_to_ansi

            style, reset = operation.args
            if reset:
                self.terminal.current_ansi_code = style_to_ansi(style)
                return

            current_style = (
                parse_sgr_sequence(self.terminal.current_ansi_code) if self.terminal.current_ansi_code else Style()
            )
            self.terminal.current_ansi_code = style_to_ansi(current_style.merge(style))
            return

        logger.debug("Unknown style operation: %s", operation)

    def _handle_query(self, operation: Operation) -> None:
        if operation.name == "CPR":
            row = self.terminal.cursor_y + 1
            col = self.terminal.cursor_x + 1
            self.terminal.respond(f"\033[{row};{col}R")
            return
        if operation.name == "DSR":
            self.terminal.respond("\033[0n")
            return
        if operation.name == "DA1":
            self.terminal.respond("\033[?62;1;6;8;9;15;18;21;22;23c")
            return
        if operation.name == "DA2":
            self.terminal.respond("\033[>1;10;0c")
            return
        if operation.name == "DECRQM":
            mode, private = operation.args
            if private:
                status = self._get_private_mode_status(mode)
            else:
                status = self._get_ansi_mode_status(mode)
            prefix = "?" if private else ""
            self.terminal.respond(f"\033[{prefix}{mode};{status}$y")
            return
        if operation.name == "OSC_FOREGROUND_COLOR":
            self.terminal.respond("\033]10;rgb:ffff/ffff/ffff\007")
            return
        if operation.name == "OSC_BACKGROUND_COLOR":
            self.terminal.respond("\033]11;rgb:0000/0000/0000\007")
            return

        logger.debug("Unknown query operation: %s", operation)

    def _handle_title(self, operation: Operation) -> None:
        (title,) = operation.args
        if operation.name == "SET_ICON_AND_WINDOW_TITLE":
            self.terminal.set_title(title)
            self.terminal.set_icon_title(title)
            return
        if operation.name == "SET_ICON_TITLE":
            self.terminal.set_icon_title(title)
            return
        if operation.name == "SET_WINDOW_TITLE":
            self.terminal.set_title(title)
            return

        logger.debug("Unknown title operation: %s", operation)

    def _handle_mode(self, operation: Operation) -> None:
        if operation.name in ("SM", "RM", "DECSET", "DECRST"):
            params, set_mode, private = operation.args
            if private:
                self._set_private_modes(params, set_mode)
            else:
                self._set_ansi_modes(params, set_mode)
            return
        if operation.name == "DECKPAM":
            self.terminal.set_mode(constants.DECKPAM_APPLICATION_KEYPAD, True)
            self.terminal.numeric_keypad = False
            return
        if operation.name == "DECKPNM":
            self.terminal.set_mode(constants.DECKPAM_APPLICATION_KEYPAD, False)
            self.terminal.numeric_keypad = True
            return

        logger.debug("Unknown mode operation: %s", operation)

    def _set_ansi_modes(self, params: tuple[int | None, ...], set_mode: bool) -> None:
        for param in params:
            if param is None:
                continue

            if param == 4:  # IRM - Insert/Replace Mode
                self.terminal.insert_mode = set_mode
            elif param == 7:  # AWM - Auto Wrap Mode
                self.terminal.auto_wrap = set_mode
            elif param == 12:  # SRM - Send/Receive Mode
                self.terminal.local_echo = not set_mode
            elif param == 20:  # LNM - Line Feed/New Line Mode
                self.terminal.linefeed_newline_mode = set_mode
            elif param == 25:  # DECTCEM - Text Cursor Enable Mode
                self.terminal.cursor_visible = set_mode

    def _set_private_modes(self, params: tuple[int | None, ...], set_mode: bool) -> None:
        for param in params:
            if param is None:
                continue

            if param == 1:  # DECCKM - Cursor Keys Mode
                self.terminal.cursor_application_mode = set_mode
            elif param == 2:  # DECANM - ANSI/VT52 Mode
                self.terminal.ansi_mode = set_mode
            elif param == 3:  # DECCOLM - 132 Column Mode
                self.terminal.resize(132 if set_mode else 80, self.terminal.height)
            elif param == 4:  # DECSCLM - Scrolling Mode
                self.terminal.scroll_mode = set_mode
            elif param == 5:  # DECSCNM - Screen Mode
                self.terminal.reverse_screen = set_mode
            elif param == 6:  # DECOM - Origin Mode
                self.terminal.origin_mode = set_mode
            elif param == 7:  # DECAWM - Auto Wrap Mode
                self.terminal.auto_wrap = set_mode
            elif param == 8:  # DECARM - Auto Repeat Mode
                self.terminal.auto_repeat = set_mode
            elif param == 9:  # X10 Mouse Tracking
                self.terminal.mouse_tracking = set_mode
            elif param == 12:  # Cursor Blinking
                self.terminal.cursor_blinking = set_mode
            elif param == 20:  # DECNLM - Line Feed/New Line Mode
                self.terminal.linefeed_newline_mode = set_mode
            elif param == 25:  # DECTCEM - Text Cursor Enable Mode
                self.terminal.cursor_visible = set_mode
            elif param == 47:  # Alternate Screen Buffer
                if set_mode:
                    self.terminal.alternate_screen_on()
                else:
                    self.terminal.alternate_screen_off()
            elif param == 66:  # DECNKM - Numeric Keypad Mode
                self.terminal.numeric_keypad = not set_mode
            elif param == 67:  # DECBKM - Backarrow Key Mode
                self.terminal.backarrow_key_sends_bs = set_mode
            elif param == 1000:  # VT200 Mouse Tracking
                self.terminal.mouse_tracking = set_mode
            elif param == 1002:  # Button Event Mouse Tracking
                self.terminal.mouse_tracking = set_mode
                self.terminal.mouse_button_tracking = set_mode
            elif param == 1003:  # Any Event Mouse Tracking
                self.terminal.mouse_tracking = set_mode
                self.terminal.mouse_any_tracking = set_mode
            elif param == 1006:  # SGR Mouse Mode
                self.terminal.mouse_sgr_mode = set_mode
            elif param == 1015:  # URXVT Mouse Mode
                self.terminal.urxvt_mouse = set_mode
            elif param == 1047:  # Alternate Screen Buffer
                if set_mode:
                    self.terminal.alternate_screen_on()
                else:
                    self.terminal.alternate_screen_off()
            elif param == 1048:  # Save/Restore Cursor
                if set_mode:
                    self.terminal.save_cursor()
                else:
                    self.terminal.restore_cursor()
            elif param == 1049:  # Alternate Screen + Save/Restore Cursor
                if set_mode:
                    self.terminal.save_cursor()
                    self.terminal.alternate_screen_on()
                else:
                    self.terminal.alternate_screen_off()
                    self.terminal.restore_cursor()
            elif param == 2004:  # Bracketed Paste Mode
                self.terminal.bracketed_paste = set_mode
            elif param == 69:  # DECKBUM - Keyboard Usage Mode
                self.terminal.keyboard_usage_mode = set_mode
            elif param == 2028:  # DECARSM - Auto Resize Mode
                self.terminal.auto_resize_mode = set_mode

    def _get_private_mode_status(self, mode: int) -> int:
        if mode == 1:
            return 1 if self.terminal.cursor_application_mode else 2
        if mode == 2:
            return 1 if self.terminal.ansi_mode else 2
        if mode == 3:
            return 1 if self.terminal.width == 132 else 2
        if mode == 6:
            return 1 if self.terminal.origin_mode else 2
        if mode == 7:
            return 1 if self.terminal.auto_wrap else 2
        if mode == 25:
            return 1 if self.terminal.cursor_visible else 2
        if mode in (47, 1047):
            return 1 if self.terminal.in_alt_screen else 2
        if mode == 1049:
            return 1 if self.terminal.in_alt_screen else 2
        if mode == 69:
            return 1 if self.terminal.keyboard_usage_mode else 2
        if mode == 2028:
            return 1 if self.terminal.auto_resize_mode else 2
        return 0

    def _get_ansi_mode_status(self, mode: int) -> int:
        if mode == 4:
            return 1 if self.terminal.insert_mode else 2
        if mode == 7:
            return 1 if self.terminal.auto_wrap else 2
        if mode == 12:
            return 1 if not self.terminal.local_echo else 2
        if mode == 20:
            return 1 if self.terminal.linefeed_newline_mode else 2
        if mode == 25:
            return 1 if self.terminal.cursor_visible else 2
        return 0
