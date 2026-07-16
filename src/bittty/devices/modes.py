"""Mode operation handler for the current Terminal state."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .. import constants
from ..operations import Operation

if TYPE_CHECKING:
    from .board import TerminalBoard

logger = logging.getLogger(__name__)


class ModeDevice:
    """Owns terminal mode state and applies mode operations."""

    def __init__(self, board: TerminalBoard) -> None:
        self.board = board
        self.terminal = board.terminal
        self.auto_wrap = True
        self.insert_mode = False
        self.application_keypad = False
        self.ansi_mode = True
        self.cursor_application_mode = False
        self.cursor_visible = True
        self.cursor_blinking = False
        self.scroll_mode = False
        self.mouse_tracking = False
        self.mouse_button_tracking = False
        self.mouse_any_tracking = False
        self.mouse_sgr_mode = False
        self.mouse_extended_mode = False
        self.urxvt_mouse = False
        self.backarrow_key_sends_bs = False
        self.auto_repeat = True
        self.numeric_keypad = True
        self.local_echo = True
        self.reverse_screen = False
        self.linefeed_newline_mode = False
        self.origin_mode = False
        self.auto_resize_mode = False
        self.keyboard_usage_mode = False
        self.bracketed_paste = False

    def handle_operation(self, operation: Operation) -> None:
        if operation.name in ("SM", "RM", "DECSET", "DECRST"):
            params, set_mode, private = operation.args
            if private:
                self.set_private_modes(params, set_mode)
            else:
                self.set_ansi_modes(params, set_mode)
            return
        if operation.name == "DECKPAM":
            self.set_mode(constants.DECKPAM_APPLICATION_KEYPAD, True)
            self.numeric_keypad = False
            return
        if operation.name == "DECKPNM":
            self.set_mode(constants.DECKPAM_APPLICATION_KEYPAD, False)
            self.numeric_keypad = True
            return

        logger.debug("Unknown mode operation: %s", operation)

    def set_mode(self, mode: int, value: bool = True, private: bool = False) -> None:
        """Set a single terminal mode."""
        if private:
            self.set_private_modes((mode,), value)
        else:
            self.set_ansi_modes((mode,), value)

    def set_ansi_modes(self, params: tuple[int | None, ...], set_mode: bool) -> None:
        for param in params:
            if param is None:
                continue

            if param == 4:
                self.insert_mode = set_mode
            elif param == 7:
                self.auto_wrap = set_mode
            elif param == 12:
                self.local_echo = not set_mode
            elif param == 20:
                self.linefeed_newline_mode = set_mode
            elif param == 25:
                self.cursor_visible = set_mode
            elif param == constants.DECKPAM_APPLICATION_KEYPAD:
                self.application_keypad = set_mode

    def set_private_modes(self, params: tuple[int | None, ...], set_mode: bool) -> None:
        for param in params:
            if param is None:
                continue

            if param == 1:
                self.cursor_application_mode = set_mode
            elif param == 2:
                self.ansi_mode = set_mode
            elif param == 3:
                self.terminal.resize(132 if set_mode else 80, self.terminal.height)
            elif param == 4:
                self.scroll_mode = set_mode
            elif param == 5:
                self.reverse_screen = set_mode
            elif param == 6:
                self.origin_mode = set_mode
            elif param == 7:
                self.auto_wrap = set_mode
            elif param == 8:
                self.auto_repeat = set_mode
            elif param == 9:
                self.mouse_tracking = set_mode
            elif param == 12:
                self.cursor_blinking = set_mode
            elif param == 20:
                self.linefeed_newline_mode = set_mode
            elif param == 25:
                self.cursor_visible = set_mode
            elif param == 47:
                if set_mode:
                    self.terminal.alternate_screen_on()
                else:
                    self.terminal.alternate_screen_off()
            elif param == 66:
                self.numeric_keypad = not set_mode
            elif param == 67:
                self.backarrow_key_sends_bs = set_mode
            elif param == 1000:
                self.mouse_tracking = set_mode
            elif param == 1002:
                self.mouse_tracking = set_mode
                self.mouse_button_tracking = set_mode
            elif param == 1003:
                self.mouse_tracking = set_mode
                self.mouse_any_tracking = set_mode
            elif param == 1006:
                self.mouse_sgr_mode = set_mode
            elif param == 1015:
                self.urxvt_mouse = set_mode
            elif param == 1047:
                if set_mode:
                    self.terminal.alternate_screen_on()
                else:
                    self.terminal.alternate_screen_off()
            elif param == 1048:
                if set_mode:
                    self.terminal.save_cursor()
                else:
                    self.terminal.restore_cursor()
            elif param == 1049:
                if set_mode:
                    self.terminal.save_cursor()
                    self.terminal.alternate_screen_on()
                else:
                    self.terminal.alternate_screen_off()
                    self.terminal.restore_cursor()
            elif param == 2004:
                self.bracketed_paste = set_mode
            elif param == 69:
                self.keyboard_usage_mode = set_mode
            elif param == 2028:
                self.auto_resize_mode = set_mode

    def get_private_mode_status(self, mode: int) -> int:
        if mode == 1:
            return 1 if self.cursor_application_mode else 2
        if mode == 2:
            return 1 if self.ansi_mode else 2
        if mode == 3:
            return 1 if self.terminal.width == 132 else 2
        if mode == 6:
            return 1 if self.origin_mode else 2
        if mode == 7:
            return 1 if self.auto_wrap else 2
        if mode == 25:
            return 1 if self.cursor_visible else 2
        if mode in (47, 1047):
            return 1 if self.terminal.in_alt_screen else 2
        if mode == 1049:
            return 1 if self.terminal.in_alt_screen else 2
        if mode == 69:
            return 1 if self.keyboard_usage_mode else 2
        if mode == 2028:
            return 1 if self.auto_resize_mode else 2
        return 0

    def get_ansi_mode_status(self, mode: int) -> int:
        if mode == 4:
            return 1 if self.insert_mode else 2
        if mode == 7:
            return 1 if self.auto_wrap else 2
        if mode == 12:
            return 1 if not self.local_echo else 2
        if mode == 20:
            return 1 if self.linefeed_newline_mode else 2
        if mode == 25:
            return 1 if self.cursor_visible else 2
        return 0
