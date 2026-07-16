"""Present events: discrete side-effects the board pushes to an attached frontend.

Screen content stays *pull* (a frontend reads capture_pane()/get_line on its own
cadence). Only these discrete events are *pushed*, through the board's DisplayPort.
Each is a plain frozen dataclass — pure data, no imports from board/devices — so
board.py can depend on this module without a cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class Bell:
    """The terminal bell rang (C0 BEL)."""


@dataclass(frozen=True)
class TitleChanged:
    """Window and/or icon title changed (OSC 0/1/2, XTWINOPS title stack)."""

    title: str
    icon_title: str


@dataclass(frozen=True)
class Notification:
    """A desktop notification was posted (OSC 9 / 777 / 99)."""

    text: str


@dataclass(frozen=True)
class ClipboardChanged:
    """A clipboard selection was set (OSC 52 write)."""

    selection: str
    text: str


@dataclass(frozen=True)
class PromptMark:
    """A shell-integration prompt/command mark (OSC 133)."""

    mark: str
    row: int


@dataclass(frozen=True)
class PointerShapeChanged:
    """The mouse-pointer shape was requested (OSC 22)."""

    shape: str


@dataclass(frozen=True)
class FontChanged:
    """The font was set (OSC 50)."""

    font: str


@dataclass(frozen=True)
class CwdChanged:
    """The reported working directory changed (OSC 7)."""

    cwd: str


@dataclass(frozen=True)
class WindowRequest:
    """A window action was requested: "raise" / "lower" / "refresh" (XTWINOPS 5/6/7)."""

    kind: str


@dataclass(frozen=True)
class WindowStateChanged:
    """Window iconify/maximize/fullscreen/position state changed (XTWINOPS)."""

    iconified: bool
    maximized: bool
    fullscreen: bool
    position: tuple[int, int]


@dataclass(frozen=True)
class ConsoleRequest:
    """A virtual-console switch was requested (linux setterm 12/15)."""

    kind: str  # "switch" / "previous"
    index: int


@dataclass(frozen=True)
class MouseModeChanged:
    """The requested mouse-tracking mode changed (derived from modes 9/1000/1002/1003)."""

    mode: str  # "off" / "basic" / "button" / "any"
    sgr: bool  # SGR (1006) encoding requested


@dataclass(frozen=True)
class CursorVisibilityChanged:
    """Text-cursor visibility changed (DECTCEM, mode 25)."""

    visible: bool


@dataclass(frozen=True)
class SyncOutputChanged:
    """Synchronized-output mode toggled (mode 2026); a frontend gates repaint on it."""

    enabled: bool


PresentEvent = Union[
    Bell,
    TitleChanged,
    Notification,
    ClipboardChanged,
    PromptMark,
    PointerShapeChanged,
    FontChanged,
    CwdChanged,
    WindowRequest,
    WindowStateChanged,
    ConsoleRequest,
    MouseModeChanged,
    CursorVisibilityChanged,
    SyncOutputChanged,
]
