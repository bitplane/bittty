"""Mouse input encoder for terminal mouse reports."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import constants

if TYPE_CHECKING:
    from .board import TerminalBoard


class MouseDevice:
    """Owns mouse presentation state and emits mouse input reports."""

    def __init__(self, board: TerminalBoard) -> None:
        self.board = board
        self.terminal = board.terminal
        self.x = 0
        self.y = 0
        self.show = False

    def input_mouse(self, x: int, y: int, button: int, event_type: str, modifiers: set[str]) -> None:
        """
        Handle mouse input, cache position, and send appropriate sequence to the host.

        Args:
            x: 1-based mouse column.
            y: 1-based mouse row.
            button: The button that was pressed/released.
            event_type: "press", "release", or "move".
            modifiers: A set of active modifiers ("shift", "meta", "ctrl").
        """
        self.x = x
        self.y = y

        is_move = event_type == "move"
        is_press_release = event_type in ("press", "release")

        if is_move and not self.terminal.mouse_any_tracking:
            return
        if is_press_release and not self.terminal.mouse_tracking:
            return

        if self.terminal.mouse_sgr_mode:
            if "shift" in modifiers:
                button |= constants.MOUSE_MOD_SHIFT
            if "meta" in modifiers:
                button |= constants.MOUSE_MOD_META
            if "ctrl" in modifiers:
                button |= constants.MOUSE_MOD_CTRL

            final_char = "m" if event_type == "release" else "M"
            if is_move:
                button = constants.MOUSE_BUTTON_MOVEMENT

            self.terminal.host.write(f"{constants.ESC}[<{button};{x};{y}{final_char}")
