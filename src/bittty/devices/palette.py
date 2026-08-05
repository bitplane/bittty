"""Palette device: owns the live colour palette and the OSC colour surface."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..operations import Operation
from .base import Device
from ..palette import RGB, build_256, format_rgb, parse_color_spec

if TYPE_CHECKING:
    from .board import Board

_SPECIALS = ("foreground", "background", "cursor")

_COLOR_STACK_MAX = 10  # bounded like xterm's other stacks (SGR, title): ten levels


class PaletteDevice(Device):
    """Holds the current 256-colour table plus fg/bg/cursor, and applies OSC colour ops."""

    def __init__(self, board: Board) -> None:
        self.board = board
        self._defaults = board.model.palette
        self._default_colors = build_256(self._defaults.base16)
        # Colour-state version: bumped after every palette operation (and reset),
        # so chromes can key colour-conversion caches on it and invalidate cheaply.
        self.generation = 0
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
            "XTPUSHCOLORS": lambda op: self.push_colors(),
            "XTPOPCOLORS": lambda op: self.pop_colors(),
            "OSC_MOUSE_FOREGROUND": lambda op: self.dynamic_color(op, "mouse_foreground", 13, "foreground"),
            "OSC_MOUSE_BACKGROUND": lambda op: self.dynamic_color(op, "mouse_background", 14, "background"),
            "OSC_HIGHLIGHT_BACKGROUND": lambda op: self.dynamic_color(op, "highlight_background", 17, "foreground"),
            "OSC_HIGHLIGHT_FOREGROUND": lambda op: self.dynamic_color(op, "highlight_foreground", 19, "background"),
            "OSC_RESET_MOUSE_FOREGROUND": lambda op: setattr(self, "mouse_foreground", None),
            "OSC_RESET_MOUSE_BACKGROUND": lambda op: setattr(self, "mouse_background", None),
            "OSC_RESET_HIGHLIGHT_BACKGROUND": lambda op: setattr(self, "highlight_background", None),
            "OSC_RESET_HIGHLIGHT_FOREGROUND": lambda op: setattr(self, "highlight_foreground", None),
            "OSC_TEK_FOREGROUND": lambda op: self.dynamic_color(op, "tek_foreground", 15, "foreground"),
            "OSC_TEK_BACKGROUND": lambda op: self.dynamic_color(op, "tek_background", 16, "background"),
            "OSC_TEK_CURSOR": lambda op: self.dynamic_color(op, "tek_cursor", 18, "cursor"),
            "OSC_RESET_TEK_FOREGROUND": lambda op: setattr(self, "tek_foreground", None),
            "OSC_RESET_TEK_BACKGROUND": lambda op: setattr(self, "tek_background", None),
            "OSC_RESET_TEK_CURSOR": lambda op: setattr(self, "tek_cursor", None),
            "OSC_SPECIAL_COLOR": self.special_color,
            "OSC_SPECIAL_COLOR_ENABLE": self.special_color_enable,
            "OSC_RESET_SPECIAL_COLOR": lambda op: self.special_colors.clear(),
        }
        # Every handler bumps the generation; a query op over-bumps, which only
        # costs the chrome one spurious cache rebuild — never a stale colour.
        self.handlers = {name: self._counted(handler) for name, handler in self.handlers.items()}

    def _counted(self, handler):
        def run(operation: Operation) -> None:
            handler(operation)
            self.generation += 1

        return run

    def special_color(self, operation: Operation) -> None:
        """OSC 5 — set or (spec == '?') query a special colour (0=bold, 1=underline, …)."""
        index, _, spec = operation.args[0].partition(";")
        try:
            idx = int(index)
        except ValueError:
            return
        if spec == "?":
            rgb = self.special_colors.get(idx)
            if rgb is not None:
                self._respond(f"5;{idx};{format_rgb(rgb)}")
            return
        rgb = parse_color_spec(spec)
        if rgb is not None:
            self.special_colors[idx] = rgb

    def special_color_enable(self, operation: Operation) -> None:
        """OSC 6 — enable or disable a special colour."""
        index, _, value = operation.args[0].partition(";")
        try:
            self.special_color_enabled[int(index)] = value not in ("0", "")
        except ValueError:
            pass

    def reset(self) -> None:
        """Restore the model's default colours plus construction overrides (RIS)."""
        self.generation += 1
        self.colors = list(self._default_colors)
        self.foreground = self._defaults.foreground
        self.background = self._defaults.background
        self.cursor = self._defaults.cursor
        # Dynamic colours (OSC 13/14/17/19); None means "use the fg/bg fallback".
        self.mouse_foreground: RGB | None = None
        self.mouse_background: RGB | None = None
        self.highlight_foreground: RGB | None = None
        self.highlight_background: RGB | None = None
        self.tek_foreground: RGB | None = None  # OSC 15/16/18 Tektronix colours
        self.tek_background: RGB | None = None
        self.tek_cursor: RGB | None = None
        self.special_colors: dict[int, RGB] = {}  # OSC 5 special-role colours
        self.special_color_enabled: dict[int, bool] = {}  # OSC 6
        self.stack: list[tuple] = []  # XTPUSHCOLORS / XTPOPCOLORS
        for slot, rgb in self.board.palette_overrides.items():
            self._set_slot(slot, rgb)

    def dynamic_color(self, operation: Operation, slot: str, cmd: int, fallback: str) -> None:
        """OSC 13/14/17/19 — set, or (data == '?') query a dynamic colour with a fg/bg fallback."""
        data = operation.args[0]
        if data == "?":
            rgb = getattr(self, slot) or getattr(self, fallback)
            self._respond(f"{cmd};{format_rgb(rgb)}")
            return
        rgb = parse_color_spec(data)
        if rgb is not None:
            setattr(self, slot, rgb)

    def push_colors(self) -> None:
        """XTPUSHCOLORS — save the whole palette (256 entries plus fg/bg/cursor)."""
        if len(self.stack) >= _COLOR_STACK_MAX:
            self.stack.pop(0)  # evict the oldest rather than grow forever
        self.stack.append((list(self.colors), self.foreground, self.background, self.cursor))

    def pop_colors(self) -> None:
        """XTPOPCOLORS — restore the palette saved by the matching XTPUSHCOLORS."""
        if self.stack:
            colors, self.foreground, self.background, self.cursor = self.stack.pop()
            self.colors = list(colors)

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
        """OSC 110/111/112 — reset the fg/bg/cursor colour to the model default."""
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
