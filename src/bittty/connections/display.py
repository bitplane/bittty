"""The display port: typed events between the board and the terminal (chrome)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from .. import constants

if TYPE_CHECKING:
    from ..caps import TerminalCaps
    from ..devices.board import Board
    from ..keys import KeyEvent
    from ..present import PresentEvent


@runtime_checkable
class Presentable(Protocol):
    """A terminal (chrome) that receives discrete present events from the board."""

    def present(self, event: PresentEvent) -> None:
        """Handle one present event."""


class DisplayPort:
    """The board's jack toward the terminal (chrome); mirrors HostPort.

    The name is the video-connector pun, kept on purpose: the one place
    "display" survives in board vocabulary. Full duplex: the board pushes
    discrete present events down; the terminal sends input events, focus
    changes, and capability reports up. When no terminal is attached
    present() is a no-op, so the board runs headless exactly as before.
    """

    def __init__(self, board: Board | None = None, terminal: Presentable | None = None) -> None:
        self.board = board
        self.terminal = terminal

    def attach(self, terminal: Presentable) -> None:
        """Attach a terminal (chrome) to receive present events."""
        self.terminal = terminal

    def detach(self) -> None:
        """Detach the current terminal."""
        self.terminal = None

    @property
    def connected(self) -> bool:
        """Whether a terminal (chrome) is attached."""
        return self.terminal is not None

    def present(self, event: PresentEvent) -> None:
        """Forward a present event to the attached terminal, if any."""
        if self.terminal is not None:
            self.terminal.present(event)

    # --- receive side: events from the terminal (chrome) --- #

    def input_key_event(self, event: KeyEvent) -> None:
        """A key event supplied by the frontend."""
        self.board.input_key_event(event)

    def input_text(self, text: str) -> None:
        """Committed text supplied by the frontend."""
        self.board.input_text(text)

    def input(self, data: str) -> None:
        """Keystrokes from the terminal, translated per keyboard modes."""
        self.board.input(data)

    def input_key(self, char: str, modifier: int = constants.KEY_MOD_NONE) -> None:
        """A key + modifier from the terminal."""
        self.board.input_key(char, modifier)

    def input_fkey(self, num: int, modifier: int = constants.KEY_MOD_NONE) -> None:
        """A function key + modifier from the terminal."""
        self.board.input_fkey(num, modifier)

    def input_numpad_key(self, key: str) -> None:
        """A numpad key from the terminal."""
        self.board.input_numpad_key(key)

    def input_paste(self, text: str, *, phase: str = "complete") -> None:
        """Pasted text from the terminal, bracketed per mode 2004."""
        self.board.input_paste(text, phase=phase)

    def input_mouse(self, x: int, y: int, button: int, event_type: str, modifiers: set[str]) -> None:
        """A mouse event from the terminal."""
        self.board.input_mouse(x, y, button, event_type, modifiers)

    def focus_in(self) -> None:
        """The box gained focus."""
        self.board.focus_in()

    def focus_out(self) -> None:
        """The box lost focus."""
        self.board.focus_out()

    def set_caps(self, caps: TerminalCaps) -> None:
        """The terminal reports what its venue can do."""
        self.board.set_caps(caps)

    def resize(self, width: int, height: int) -> None:
        """Report a completed outer-terminal resize to the board."""
        self.board.resize_from_frontend(width, height)
