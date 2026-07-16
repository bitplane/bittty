"""Palette device: owns the live colour palette and the OSC colour surface."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..operations import Operation
from ..palette import RGB, build_256, format_rgb, parse_color_spec

if TYPE_CHECKING:
    from .board import TerminalBoard

_SPECIALS = ("foreground", "background", "cursor")


class PaletteDevice:
    """Holds the current 256-colour table plus fg/bg/cursor, and applies OSC colour ops."""

    def __init__(self, board: TerminalBoard) -> None:
        self.board = board
        self._defaults = board.personality.palette
        self._default_colors = build_256(self._defaults.base16)
        self.reset()
        self.handlers = {
            "OSC_SET_PALETTE": self.set_palette,
            "OSC_FOREGROUND": lambda op: self.set_or_query_special(op, "foreground", 10),
            "OSC_BACKGROUND": lambda op: self.set_or_query_special(op, "background", 11),
            "OSC_CURSOR": lambda op: self.set_or_query_special(op, "cursor", 12),
            "OSC_RESET_PALETTE": self.reset_palette,
            "OSC_RESET_FOREGROUND": lambda op: self.reset_special("foreground"),
            "OSC_RESET_BACKGROUND": lambda op: self.reset_special("background"),
            "OSC_RESET_CURSOR": lambda op: self.reset_special("cursor"),
            "LINUX_PALETTE_SET": self.set_linux_palette,
            "LINUX_PALETTE_RESET": lambda op: self.reset(),
        }

    def reset(self) -> None:
        """Restore the personality's default colours plus construction overrides (RIS)."""
        self.colors = list(self._default_colors)
        self.foreground = self._defaults.foreground
        self.background = self._defaults.background
        self.cursor = self._defaults.cursor
        for slot, rgb in self.board.palette_overrides.items():
            self._set_slot(slot, rgb)

    def _set_slot(self, slot, rgb: RGB) -> None:
        if slot in _SPECIALS:
            setattr(self, slot, rgb)
        elif isinstance(slot, int) and 0 <= slot < 256:
            self.colors[slot] = rgb

    def resolve(self, color) -> RGB | None:
        """Resolve a Style colour to concrete RGB. None means "use the default fg/bg"."""
        if color is None or color.mode == "default":
            return None
        if color.mode == "indexed":
            index = color.value
            return self.colors[index] if 0 <= index < 256 else None
        if color.mode == "rgb":
            return color.value
        return None

    def _respond(self, body: str) -> None:
        self.board.host.write(f"\033]{body}\007", flush=True)

    def set_palette(self, operation: Operation) -> None:
        """OSC 4 ; n ; spec [; n ; spec ...] — set or (spec == '?') query palette entries."""
        fields = operation.args[0].split(";")
        for i in range(0, len(fields) - 1, 2):
            try:
                index = int(fields[i])
            except ValueError:
                continue
            if not 0 <= index < 256:
                continue
            spec = fields[i + 1]
            if spec == "?":
                self._respond(f"4;{index};{format_rgb(self.colors[index])}")
            else:
                rgb = parse_color_spec(spec)
                if rgb is not None:
                    self.colors[index] = rgb

    def set_or_query_special(self, operation: Operation, slot: str, cmd: int) -> None:
        """OSC 10/11/12 — set or (data == '?') query the fg/bg/cursor colour."""
        data = operation.args[0]
        if data == "?":
            self._respond(f"{cmd};{format_rgb(getattr(self, slot))}")
            return
        rgb = parse_color_spec(data)
        if rgb is not None:
            setattr(self, slot, rgb)

    def reset_palette(self, operation: Operation) -> None:
        """OSC 104 — reset all palette entries, or just the listed indices."""
        data = operation.args[0].strip()
        if not data:
            self.colors = list(self._default_colors)
            return
        for field in data.split(";"):
            try:
                index = int(field)
            except ValueError:
                continue
            if 0 <= index < 256:
                self.colors[index] = self._default_colors[index]

    def reset_special(self, slot: str) -> None:
        """OSC 110/111/112 — reset the fg/bg/cursor colour to the personality default."""
        setattr(self, slot, getattr(self._defaults, slot))

    def set_linux_palette(self, operation: Operation) -> None:
        """ESC ] P nrrggbb — the linux console's own single-entry palette set."""
        payload = operation.args[0]
        if len(payload) != 7:
            return
        try:
            index = int(payload[0], 16)
            r, g, b = int(payload[1:3], 16), int(payload[3:5], 16), int(payload[5:7], 16)
        except ValueError:
            return
        self.colors[index] = (r, g, b)

    def handle_operation(self, operation: Operation) -> None:
        handler = self.handlers.get(operation.name)
        if handler is not None:
            handler(operation)
