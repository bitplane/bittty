"""The Terminal abstract base: the chrome a human looks at.

A concrete terminal *is-a* Terminal and *has-a* Board (composition), which it is
given or builds. It plugs itself into the board's display port and talks to the
board only through it (`self.port`): present events arrive at typed hooks, input
and TerminalCaps go up, and the screen is read from it, with `damaged_rows()`
saying what to repaint. Given a scrollback store, it keeps the rows that scroll
off the board there and can show history above the screen. Every hook defaults to a no-op, so
adding a new event type can never break an existing terminal — it just grows
the surface with another optional override.

The board never imports this module: the boundary only ever runs
terminal -> board, never the reverse.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from ..caps import TerminalCaps
from ..video import Cell
from ..present import (
    AmbiguousWidthChanged,
    Bell,
    ChildExited,
    ChromeResourcesChanged,
    ClipboardChanged,
    ConsoleRequest,
    CursorBlinkChanged,
    CursorVisibilityChanged,
    CwdChanged,
    FontChanged,
    GraphemeClusteringChanged,
    StatusLineChanged,
    PointerModeChanged,
    KeyboardIndicatorChanged,
    KeyboardLockChanged,
    MouseCaptureChanged,
    Notification,
    PointerShapeChanged,
    PresentEvent,
    PromptMark,
    ReverseScreenChanged,
    RowsScrolledOff,
    ScreenChanged,
    ScrollbackCleared,
    SmoothScrollChanged,
    SyncOutputChanged,
    TitleChanged,
    WindowRequest,
    WindowStateChanged,
)
from .scrollback import Scrollback, ScrollbackLine

if TYPE_CHECKING:
    from ..connections import DisplayPort
    from ..devices.board import Board
    from ..video import Line, Video


class Terminal:
    """Abstract base for terminals (chrome). Compose a Board; override the hooks you need."""

    # True to be sent RowsScrolledOff and ScrollbackCleared: set when given a store.
    keeps_scrollback = False

    def __init__(self, board: Board, scrollback: Scrollback | None = None) -> None:
        self.board = board
        self.scrollback = scrollback
        self.keeps_scrollback = scrollback is not None
        # Scrolled back, the top row shown, as (line, row within it) so it holds still
        # as output arrives and as the width changes; None shows the live screen.
        self.view_top: tuple[int, int] | None = None
        self._seen_page: Video | None = None  # the page painted last
        self._seen_gen = -1  # its generation when painted

    @property
    def port(self) -> DisplayPort:
        """The jack to the board: input goes up it, and the screen (a connections.Screen) is read from it."""
        return self.board.display

    def damaged_rows(self) -> Sequence[int]:
        """The rows of the displayed page changed since the last call; all of them after a page flip.

        Call it once per paint: asking is what marks the rows seen.
        """
        page = self.port.page
        rows = page.dirty_rows(self._seen_gen) if page is self._seen_page else range(page.height)
        self._seen_page, self._seen_gen = page, page.observe()
        return rows

    # --- the view: history above the screen --- #

    def view_offset(self) -> int:
        """How many rows the view sits above the live screen."""
        if self.view_top is None:
            return 0
        history = self.scrollback.width(self.port.width)
        line, within = self.view_top
        top = history.row_for(max(line, self.scrollback.first)) + within
        return max(0, len(history) - top)

    def scroll_view(self, rows: int) -> None:
        """Move the view `rows` down (negative: back into history), no further than either end."""
        history = self.scrollback.width(self.port.width)
        top = max(0, len(history) - self.view_offset() + rows)
        self.view_top = history.line_at(top) if top < len(history) else None
        self._seen_page = None  # everything shown moves

    def scroll_to_bottom(self) -> None:
        """Show the live screen."""
        if self.view_top is not None:
            self.view_top, self._seen_page = None, None

    def view_rows(self) -> list[Sequence[Cell]]:
        """The rows to show, top to bottom: history the view is scrolled over, then the screen."""
        port = self.port
        offset = self.view_offset()
        history = self.scrollback.width(port.width) if offset else ()
        shown = min(offset, port.height)
        top = len(history) - offset
        above = [history[row] for row in range(top, top + shown)]
        return above + [port.page.line(y).cells for y in range(port.height - shown)]

    # --- wiring --- #

    def attach(self) -> None:
        """Plug this terminal into its board's display port."""
        self.board.attach_display(self)

    def detach(self) -> None:
        """Unplug from the board's display port."""
        self.board.detach_display()

    def set_caps(self, caps: TerminalCaps) -> None:
        """Push the real terminal's capabilities down to the board."""
        self.board.display.set_caps(caps)

    # --- present dispatch --- #

    def present(self, event: PresentEvent) -> None:
        """Route a present event to its typed hook (unknown types are ignored)."""
        handler = _DISPATCH.get(type(event))
        if handler is not None:
            handler(self, event)

    # --- hooks (all default no-op; override what you care about) --- #

    def on_screen_changed(self) -> None: ...

    def on_rows_scrolled_off(self, lines: tuple[Line, ...]) -> None:
        """Keep the rows in the scrollback, a line's end without its trailing blanks."""
        for line in lines:
            self.scrollback.append(ScrollbackLine.of(line.cells, not line.wrapped, line.attribute), line.wrapped)

    def on_scrollback_cleared(self) -> None:
        self.scrollback.clear()
        self.view_top, self._seen_page = None, None

    def on_child_exited(self, returncode: int | None) -> None: ...
    def on_bell(self) -> None: ...
    def on_title(self, title: str, icon_title: str) -> None: ...
    def on_notify(self, text: str) -> None: ...
    def on_clipboard(self, selection: str, text: str) -> None: ...
    def on_prompt_mark(self, mark: str, row: int) -> None: ...
    def on_pointer(self, shape: str) -> None: ...
    def on_font(self, font: str) -> None: ...
    def on_cwd(self, cwd: str) -> None: ...
    def on_window_request(self, kind: str) -> None: ...
    def on_keyboard_lock(self, locked: bool) -> None: ...
    def on_keyboard_indicator(self, num_lock: bool, caps_lock: bool, scroll_lock: bool) -> None: ...
    def on_window_state(self, event: WindowStateChanged) -> None: ...
    def on_console_request(self, kind: str, index: int) -> None: ...
    def on_mouse_capture(self, mode: str) -> None: ...
    def on_cursor_visible(self, visible: bool) -> None: ...
    def on_cursor_blink(self, enabled: bool) -> None: ...
    def on_reverse_screen(self, enabled: bool) -> None: ...
    def on_sync_output(self, enabled: bool) -> None: ...
    def on_ambiguous_width(self, width: int) -> None: ...
    def on_grapheme_clustering(self, enabled: bool) -> None: ...
    def on_status_line(self, kind: str) -> None: ...
    def on_pointer_mode(self, mode: int) -> None: ...
    def on_chrome_resources(self, enabled: frozenset[str]) -> None: ...
    def on_smooth_scroll(self, enabled: bool) -> None: ...


# Event type -> adapter unpacking its fields into the corresponding hook.
_DISPATCH = {
    ScreenChanged: lambda d, e: d.on_screen_changed(),
    RowsScrolledOff: lambda d, e: d.on_rows_scrolled_off(e.lines),
    ScrollbackCleared: lambda d, e: d.on_scrollback_cleared(),
    ChildExited: lambda d, e: d.on_child_exited(e.returncode),
    Bell: lambda d, e: d.on_bell(),
    TitleChanged: lambda d, e: d.on_title(e.title, e.icon_title),
    Notification: lambda d, e: d.on_notify(e.text),
    ClipboardChanged: lambda d, e: d.on_clipboard(e.selection, e.text),
    PromptMark: lambda d, e: d.on_prompt_mark(e.mark, e.row),
    PointerShapeChanged: lambda d, e: d.on_pointer(e.shape),
    FontChanged: lambda d, e: d.on_font(e.font),
    CwdChanged: lambda d, e: d.on_cwd(e.cwd),
    WindowRequest: lambda d, e: d.on_window_request(e.kind),
    KeyboardLockChanged: lambda d, e: d.on_keyboard_lock(e.locked),
    KeyboardIndicatorChanged: lambda d, e: d.on_keyboard_indicator(e.num_lock, e.caps_lock, e.scroll_lock),
    WindowStateChanged: lambda d, e: d.on_window_state(e),
    ConsoleRequest: lambda d, e: d.on_console_request(e.kind, e.index),
    MouseCaptureChanged: lambda d, e: d.on_mouse_capture(e.mode),
    CursorVisibilityChanged: lambda d, e: d.on_cursor_visible(e.visible),
    CursorBlinkChanged: lambda d, e: d.on_cursor_blink(e.enabled),
    ReverseScreenChanged: lambda d, e: d.on_reverse_screen(e.enabled),
    SyncOutputChanged: lambda d, e: d.on_sync_output(e.enabled),
    AmbiguousWidthChanged: lambda d, e: d.on_ambiguous_width(e.width),
    GraphemeClusteringChanged: lambda d, e: d.on_grapheme_clustering(e.enabled),
    StatusLineChanged: lambda d, e: d.on_status_line(e.kind),
    PointerModeChanged: lambda d, e: d.on_pointer_mode(e.mode),
    ChromeResourcesChanged: lambda d, e: d.on_chrome_resources(e.enabled),
    SmoothScrollChanged: lambda d, e: d.on_smooth_scroll(e.enabled),
}
