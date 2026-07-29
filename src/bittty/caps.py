"""TerminalCaps: physical facts about the real terminal, pushed *up* by the chrome.

The backend answers the child's physical-fact queries (window/cell pixel size,
background colour) from these and uses the destination's measured ambiguous
character width when a terminal (chrome) has supplied it. Every field defaults
to "unknown" (None / "unknown"), meaning "change nothing" — so a board with no
attached terminal behaves exactly as it does today.

Graphics-capability flags (sixel / kitty / iTerm images) are deliberately absent
until graphics modes are on the table; there is nothing to reconcile without them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class TerminalCaps:
    """What the real terminal can actually do (terminal -> board)."""

    color_depth: str = "unknown"  # "monochrome" / "16" / "256" / "truecolor" / "unknown"
    cell_px: tuple[int, int] | None = None  # character cell size in pixels (CSI 16 t)
    window_px: tuple[int, int] | None = None  # window size in pixels (CSI 14 t)
    background: tuple[int, int, int] | None = None  # actual background colour (OSC 11)
    ambiguous_width: Literal[1, 2] | None = None  # measured width of East Asian Ambiguous characters

    def __post_init__(self) -> None:
        if self.ambiguous_width not in (None, 1, 2):
            raise ValueError("ambiguous_width must be 1, 2, or None")

    @classmethod
    def unknown(cls) -> "TerminalCaps":
        """Caps that assert nothing — the backend keeps its current behaviour."""
        return cls()
