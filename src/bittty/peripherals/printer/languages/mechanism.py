"""The physical printer mechanism: settings that outlive a language switch."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from ._bytes import _NON_PRINTABLE_BYTES
from .state import (
    PrintDirection,
    PrinterCharacterState,
    PrinterRendition,
    _PrinterLayoutCommand,
    _PrinterReportCommand,
)


class PrinterMechanism:
    """The physical machine: what it is set to, and what the print head does.

    A language is a decoder that drives this; the mechanism outlives the switch
    between them, which is why entering and leaving IBM ProPrinter emulation
    snapshots and restores exactly this state.
    """

    __slots__ = (
        "_on_bit_image",
        "_on_control",
        "_on_crm_token",
        "_on_font_download",
        "_on_layout",
        "_on_printable",
        "_on_report",
        "_on_reset",
        "autowrap",
        "carriage_return_new_line",
        "characters",
        "control_representation",
        "direction",
        "line_feed_new_line",
        "pitch_from_font",
        "position_unit_mode",
        "proportional_spacing",
        "rendition",
    )

    def __init__(
        self,
        *,
        on_printable: Callable[[bytes], None] | None = None,
        on_control: Callable[[int], None] | None = None,
        on_crm_token: Callable[[bytes, str], None] | None = None,
        on_layout: Callable[[_PrinterLayoutCommand, tuple[int, ...]], None] | None = None,
        on_report: Callable[[_PrinterReportCommand], None] | None = None,
        on_bit_image: Callable[[int, int, bool, bytes], None] | None = None,
        on_font_download: Callable[[bytes], None] | None = None,
        on_reset: Callable[[], None] | None = None,
    ) -> None:
        self._on_printable = on_printable
        self._on_control = on_control
        self._on_crm_token = on_crm_token
        self._on_layout = on_layout
        self._on_report = on_report
        self._on_bit_image = on_bit_image
        self._on_font_download = on_font_download
        self._on_reset = on_reset
        self.reset_modes()

    # --- physical state ---------------------------------------------------- #

    def reset_modes(self) -> None:
        """Return every physical setting to power-on."""
        self.direction = PrintDirection.BIDIRECTIONAL
        self.proportional_spacing = False
        self.pitch_from_font = False
        self.carriage_return_new_line = False
        self.autowrap = True
        self.control_representation = False
        self.line_feed_new_line = False
        self.position_unit_mode = False
        self.rendition = PrinterRendition()
        self.characters = PrinterCharacterState()

    def snapshot(self) -> tuple:
        """Capture the settings that survive a language switch."""
        return (
            self.direction,
            self.proportional_spacing,
            self.pitch_from_font,
            self.carriage_return_new_line,
            self.autowrap,
            self.control_representation,
            self.line_feed_new_line,
            self.position_unit_mode,
            self.rendition,
            self.characters,
        )

    def restore(self, snapshot: tuple) -> None:
        """Reinstate a snapshot taken before a language switch."""
        (
            self.direction,
            self.proportional_spacing,
            self.pitch_from_font,
            self.carriage_return_new_line,
            self.autowrap,
            self.control_representation,
            self.line_feed_new_line,
            self.position_unit_mode,
            self.rendition,
            self.characters,
        ) = snapshot

    # --- print head -------------------------------------------------------- #

    def print(self, data: bytes) -> None:
        """Print bytes, consuming any pending single shift as they pass under the head."""
        printable = data.translate(None, _NON_PRINTABLE_BYTES)
        if not printable:
            return
        shifted_index = self._single_shifted_index(printable)
        if shifted_index is None:
            if self._on_printable is not None:
                self._on_printable(printable)
            return
        pending = self.characters
        if shifted_index:
            self.characters = replace(pending, single_shift=None)
            if self._on_printable is not None:
                self._on_printable(printable[:shifted_index])
            self.characters = pending
        if self._on_printable is not None:
            self._on_printable(printable[shifted_index : shifted_index + 1])
        self.characters = replace(pending, single_shift=None)
        if shifted_index + 1 < len(printable) and self._on_printable is not None:
            self._on_printable(printable[shifted_index + 1 :])

    def print_verbatim(self, data: bytes) -> None:
        """Print bytes exactly as given, without character-set interpretation."""
        if data and self._on_printable is not None:
            self._on_printable(data)

    def _single_shifted_index(self, data: bytes) -> int | None:
        gset = self.characters.single_shift
        if gset is None:
            return None
        is_96 = self.characters.g_sets[gset].size == 96
        return next(
            (
                index
                for index, byte in enumerate(data)
                if byte >= 0xA0 or 0x21 <= byte <= 0x7E or is_96 and byte == 0x20
            ),
            None,
        )

    def control(self, byte: int) -> None:
        if self._on_control is not None:
            self._on_control(byte)

    def layout(self, command: _PrinterLayoutCommand, *parameters: int) -> None:
        if self._on_layout is not None:
            self._on_layout(command, parameters)

    def report(self, command: _PrinterReportCommand) -> None:
        if self._on_report is not None:
            self._on_report(command)

    def power_on_reset(self) -> None:
        """Announce that the mechanism performed a power-on reset."""
        if self._on_reset is not None:
            self._on_reset()

    def crm_token(self, raw: bytes, token: str) -> None:
        if self._on_crm_token is not None:
            self._on_crm_token(raw, token)

    def bit_image(self, *specification) -> None:
        if self._on_bit_image is not None:
            self._on_bit_image(*specification)

    def font_download(self, data: bytes) -> None:
        if self._on_font_download is not None:
            self._on_font_download(data)

    @property
    def accepts_bit_images(self) -> bool:
        """Whether anything is listening for bit-image data."""
        return self._on_bit_image is not None
