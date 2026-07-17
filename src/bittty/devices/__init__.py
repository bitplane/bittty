"""Device adapters for applying parser operations."""

from .board import Board
from .charset import CharsetDevice
from .control import ControlDevice
from .cursor import CursorDevice
from .keyboard import KeyboardDevice
from .modes import ModeDevice
from .mouse import MouseDevice
from .query import QueryDevice
from .screen import ScreenDevice
from .style import StyleDevice
from .title import TitleDevice

__all__ = [
    "CharsetDevice",
    "ControlDevice",
    "CursorDevice",
    "KeyboardDevice",
    "ModeDevice",
    "MouseDevice",
    "QueryDevice",
    "ScreenDevice",
    "StyleDevice",
    "Board",
    "TitleDevice",
]
