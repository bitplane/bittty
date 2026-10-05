"""The display port: the board's jack toward the terminal (chrome).

Three things cross it. Present events go down, pushed: what would otherwise be lost.
Input goes up. And the screen is read across it, pulled: what is still there, read on
the terminal's own cadence. A terminal needs nothing from the board but this jack and
the board's power switch (start_process/stop_process).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from .. import constants

if TYPE_CHECKING:
    from ..caps import TerminalCaps
    from ..devices.board import Board
    from ..keyboard.keys import KeyEvent
    from ..present import PresentEvent
    from ..video import Video


@runtime_checkable
class Presentable(Protocol):
    """A terminal (chrome) that receives discrete present events from the board."""

    # Whether it wants RowsScrolledOff. Copying each row as it leaves costs the board
    # time on every line feed, so a terminal with no scrollback to fill says no.
    keeps_scrollback: bool

    def present(self, event: PresentEvent) -> None:
        """Handle one present event."""


@runtime_checkable
class Screen(Protocol):
    """What a terminal reads to paint: the displayed page and where to draw the cursor.

    The board's DisplayPort is one; anything else that can answer these (a recording
    played back without a board, say) can stand in for it.
    """

    @property
    def width(self) -> int:
        """Columns on the page."""

    @property
    def height(self) -> int:
        """Rows on the page."""

    @property
    def page(self) -> Video:
        """The page on display: read it, never write it. Its generations say which rows changed."""

    @property
    def cursor(self) -> tuple[int, int] | None:
        """The cursor's (column, row) on the displayed page, or None when none should be drawn."""


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

    @property
    def keeps_scrollback(self) -> bool:
        """Whether the attached terminal wants the rows that scroll off the top."""
        return self.terminal is not None and self.terminal.keeps_scrollback

    def present(self, event: PresentEvent) -> None:
        """Forward a present event to the attached terminal, if any."""
        if self.terminal is not None:
            self.terminal.present(event)

    # --- the screen, read by the terminal (chrome) --- #

    @property
    def width(self) -> int:
        return self.board.width

    @property
    def height(self) -> int:
        return self.board.height

    @property
    def page(self) -> Video:
        return self.board.blitter.main_page  # never the status line: board.capture_status_line() reads that

    @property
    def cursor(self) -> tuple[int, int] | None:
        board = self.board
        if not (board.modes.cursor_visible and board.blitter.cursor_on_display):
            return None
        return board.cursor.display_x, board.cursor.y

    # --- what the terminal needs to decode its venue's input --- #

    @property
    def kitty_flags(self) -> int:
        """The Kitty keyboard enhancements the child has asked for, on the active screen."""
        return self.board.keyboard.kitty_flags

    @property
    def keyboard_selected(self) -> bool:
        """Whether an xterm keyboard (Sun/HP/SCO/legacy/VT220) replaces the model's keymap."""
        return self.board.keyboard.keyboard_selected

    @property
    def escape_is_key(self) -> bool:
        """Whether a lone ESC is a key press rather than a sequence's start (mintty 7727/7728)."""
        modes = self.board.modes
        return modes.application_escape or modes.escape_sends_fs

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
