"""Mode operation handler for the current Terminal state."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .. import constants
from ..operations import Operation

if TYPE_CHECKING:
    from ..terminal import Terminal

logger = logging.getLogger(__name__)


class ModeDevice:
    """Applies terminal mode operations to the current Terminal implementation."""

    def __init__(self, terminal: Terminal) -> None:
        self.terminal = terminal

    def handle_operation(self, operation: Operation) -> None:
        if operation.name in ("SM", "RM", "DECSET", "DECRST"):
            params, set_mode, private = operation.args
            if private:
                self.set_private_modes(params, set_mode)
            else:
                self.set_ansi_modes(params, set_mode)
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

    def set_ansi_modes(self, params: tuple[int | None, ...], set_mode: bool) -> None:
        for param in params:
            if param is None:
                continue

            if param == 4:
                self.terminal.insert_mode = set_mode
            elif param == 7:
                self.terminal.auto_wrap = set_mode
            elif param == 12:
                self.terminal.local_echo = not set_mode
            elif param == 20:
                self.terminal.linefeed_newline_mode = set_mode
            elif param == 25:
                self.terminal.cursor_visible = set_mode

    def set_private_modes(self, params: tuple[int | None, ...], set_mode: bool) -> None:
        for param in params:
            if param is None:
                continue

            if param == 1:
                self.terminal.cursor_application_mode = set_mode
            elif param == 2:
                self.terminal.ansi_mode = set_mode
            elif param == 3:
                self.terminal.resize(132 if set_mode else 80, self.terminal.height)
            elif param == 4:
                self.terminal.scroll_mode = set_mode
            elif param == 5:
                self.terminal.reverse_screen = set_mode
            elif param == 6:
                self.terminal.origin_mode = set_mode
            elif param == 7:
                self.terminal.auto_wrap = set_mode
            elif param == 8:
                self.terminal.auto_repeat = set_mode
            elif param == 9:
                self.terminal.mouse_tracking = set_mode
            elif param == 12:
                self.terminal.cursor_blinking = set_mode
            elif param == 20:
                self.terminal.linefeed_newline_mode = set_mode
            elif param == 25:
                self.terminal.cursor_visible = set_mode
            elif param == 47:
                if set_mode:
                    self.terminal.alternate_screen_on()
                else:
                    self.terminal.alternate_screen_off()
            elif param == 66:
                self.terminal.numeric_keypad = not set_mode
            elif param == 67:
                self.terminal.backarrow_key_sends_bs = set_mode
            elif param == 1000:
                self.terminal.mouse_tracking = set_mode
            elif param == 1002:
                self.terminal.mouse_tracking = set_mode
                self.terminal.mouse_button_tracking = set_mode
            elif param == 1003:
                self.terminal.mouse_tracking = set_mode
                self.terminal.mouse_any_tracking = set_mode
            elif param == 1006:
                self.terminal.mouse_sgr_mode = set_mode
            elif param == 1015:
                self.terminal.urxvt_mouse = set_mode
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
                self.terminal.bracketed_paste = set_mode
            elif param == 69:
                self.terminal.keyboard_usage_mode = set_mode
            elif param == 2028:
                self.terminal.auto_resize_mode = set_mode

    def get_private_mode_status(self, mode: int) -> int:
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

    def get_ansi_mode_status(self, mode: int) -> int:
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
