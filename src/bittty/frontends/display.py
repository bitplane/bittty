"""The Display abstract base: the blessed frontend contract.

A concrete frontend *is-a* Display and *has-a* Terminal (composition). It attaches
itself as the board's display port, pushes DisplayCaps up, and receives discrete
side-effects through present(), which dispatches each PresentEvent to a typed hook.
Every hook defaults to a no-op, so adding a new event type can never break an
existing frontend — it just grows the surface with another optional override.

The backend (`Terminal`) never imports this module: the boundary only ever runs
frontend -> backend, never the reverse.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..caps import DisplayCaps
from ..present import (
    Bell,
    ClipboardChanged,
    ConsoleRequest,
    CursorVisibilityChanged,
    CwdChanged,
    FontChanged,
    MouseModeChanged,
    Notification,
    PointerShapeChanged,
    PresentEvent,
    PromptMark,
    SyncOutputChanged,
    TitleChanged,
    WindowRequest,
    WindowStateChanged,
)

if TYPE_CHECKING:
    from ..terminal import Terminal


class Display:
    """Abstract base for frontends. Compose a Terminal; override the hooks you need."""

    def __init__(self, terminal: "Terminal") -> None:
        self.terminal = terminal

    # --- wiring --- #

    def attach(self) -> None:
        """Attach this frontend to its terminal's display port."""
        self.terminal.attach_display(self)

    def detach(self) -> None:
        """Detach from the terminal's display port."""
        self.terminal.detach_display()

    def set_caps(self, caps: DisplayCaps) -> None:
        """Push the real display's capabilities down to the backend."""
        self.terminal.board.set_display_caps(caps)

    # --- present dispatch --- #

    def present(self, event: PresentEvent) -> None:
        """Route a present event to its typed hook (unknown types are ignored)."""
        handler = _DISPATCH.get(type(event))
        if handler is not None:
            handler(self, event)

    # --- hooks (all default no-op; override what you care about) --- #

    def on_bell(self) -> None: ...
    def on_title(self, title: str, icon_title: str) -> None: ...
    def on_notify(self, text: str) -> None: ...
    def on_clipboard(self, selection: str, text: str) -> None: ...
    def on_prompt_mark(self, mark: str, row: int) -> None: ...
    def on_pointer(self, shape: str) -> None: ...
    def on_font(self, font: str) -> None: ...
    def on_cwd(self, cwd: str) -> None: ...
    def on_window_request(self, kind: str) -> None: ...
    def on_window_state(self, event: WindowStateChanged) -> None: ...
    def on_console_request(self, kind: str, index: int) -> None: ...
    def on_mouse_mode(self, mode: str, sgr: bool) -> None: ...
    def on_cursor_visible(self, visible: bool) -> None: ...
    def on_sync_output(self, enabled: bool) -> None: ...


# Event type -> adapter unpacking its fields into the corresponding hook.
_DISPATCH = {
    Bell: lambda d, e: d.on_bell(),
    TitleChanged: lambda d, e: d.on_title(e.title, e.icon_title),
    Notification: lambda d, e: d.on_notify(e.text),
    ClipboardChanged: lambda d, e: d.on_clipboard(e.selection, e.text),
    PromptMark: lambda d, e: d.on_prompt_mark(e.mark, e.row),
    PointerShapeChanged: lambda d, e: d.on_pointer(e.shape),
    FontChanged: lambda d, e: d.on_font(e.font),
    CwdChanged: lambda d, e: d.on_cwd(e.cwd),
    WindowRequest: lambda d, e: d.on_window_request(e.kind),
    WindowStateChanged: lambda d, e: d.on_window_state(e),
    ConsoleRequest: lambda d, e: d.on_console_request(e.kind, e.index),
    MouseModeChanged: lambda d, e: d.on_mouse_mode(e.mode, e.sgr),
    CursorVisibilityChanged: lambda d, e: d.on_cursor_visible(e.visible),
    SyncOutputChanged: lambda d, e: d.on_sync_output(e.enabled),
}
