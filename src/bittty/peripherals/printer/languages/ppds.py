"""IBM ProPrinter (PPDS) decoder."""

from __future__ import annotations

from dataclasses import replace

from ._bytes import (
    _ESC,
    _IBM_BRACKET_LENGTH_COMMANDS,
    _IBM_SPECIAL_BYTES,
)
from .control import LanguageControl
from .mechanism import PrinterMechanism
from .state import (
    PrintDirection,
    PrinterDensity,
    PrinterLanguage,
    PrinterScript,
    PrinterUnderline,
    _PrinterLayoutCommand,
)


class PpdsParser:
    """IBM ProPrinter (PPDS) decoder driving the same mechanism."""

    def __init__(self, mechanism: PrinterMechanism, control: LanguageControl) -> None:
        self._mechanism = mechanism
        self._control = control
        self._ibm_pending = bytearray()
        self._ibm_binary = bytearray()
        self._ibm_code_page = 437
        self.reset()

    def reset(self) -> None:
        """Return every ProPrinter mode to power-on; the code page persists."""
        self._ibm_state = "ground"
        self._ibm_command = 0
        self._ibm_expected = 0
        self._ibm_pending.clear()
        self._ibm_binary.clear()
        self._ibm_pending_line_spacing = 36
        self._ibm_line_double_width = False
        self._ibm_continuous_double_width = False
        self._ibm_double_height = False
        self._ibm_character_set = 1
        self._ibm_selected = True
        self._ibm_downloaded_font = False

    # --- state this language contributes to VirtualPrinterState ------------- #

    @property
    def code_page(self) -> int:
        return self._ibm_code_page

    @code_page.setter
    def code_page(self, value: int) -> None:
        self._ibm_code_page = int(value)

    @property
    def double_width(self) -> bool:
        return self._ibm_line_double_width or self._ibm_continuous_double_width

    @property
    def double_height(self) -> bool:
        return self._ibm_double_height

    @property
    def character_set(self) -> int:
        return self._ibm_character_set

    @property
    def selected(self) -> bool:
        return self._ibm_selected

    @property
    def downloaded_font(self) -> bool:
        return self._ibm_downloaded_font

    def feed(self, data: bytes, offset: int) -> int:
        size = len(data)
        while offset < size and self._control.language is PrinterLanguage.IBM_PROPRINTER:
            if not self._ibm_selected:
                selected = data.find(b"\x11", offset)
                if selected == -1:
                    return size
                offset = selected + 1
                self._ibm_selected = True
                continue

            if self._ibm_state == "ground":
                byte = data[offset]
                offset += 1
                if byte == _ESC:
                    self._ibm_state = "escape"
                elif byte in (0x00, 0x13):
                    pass
                elif byte == 0x07:
                    self._mechanism.layout(_PrinterLayoutCommand.IBM_BELL)
                elif byte in (0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D):
                    if byte in (0x0A, 0x0B, 0x0C, 0x0D):
                        self._set_ibm_line_double_width(False)
                    self._mechanism.control(byte)
                elif byte == 0x0E:
                    self._set_ibm_line_double_width(True)
                elif byte == 0x0F:
                    self._mechanism.layout(_PrinterLayoutCommand.IBM_HORIZONTAL_PITCH, 171)
                elif byte == 0x11:
                    self._ibm_selected = True
                elif byte == 0x12:
                    self._mechanism.layout(_PrinterLayoutCommand.IBM_HORIZONTAL_PITCH, 100)
                elif byte in (0x14, 0x18):
                    self._set_ibm_line_double_width(False)
                    if byte == 0x18:
                        self._mechanism.layout(_PrinterLayoutCommand.IBM_CANCEL_LINE)
                else:
                    start = offset - 1
                    next_special = size
                    for marker in _IBM_SPECIAL_BYTES:
                        found = data.find(marker, offset)
                        if found != -1 and found < next_special:
                            next_special = found
                    self._mechanism.print(data[start:next_special])
                    offset = next_special
                continue

            if self._ibm_state == "verbatim":
                take = min(self._ibm_expected, size - offset)
                self._mechanism.print_verbatim(data[offset : offset + take])
                offset += take
                self._ibm_expected -= take
                if self._ibm_expected == 0:
                    self._ibm_state = "ground"
                continue

            if self._ibm_state == "discard":
                take = min(self._ibm_expected, size - offset)
                offset += take
                self._ibm_expected -= take
                if self._ibm_expected == 0:
                    self._ibm_state = "ground"
                continue

            if self._ibm_state == "bracket-data":
                take = min(self._ibm_expected, size - offset)
                retained = min(take, max(0, 4 - len(self._ibm_pending)))
                self._ibm_pending.extend(data[offset : offset + retained])
                offset += take
                self._ibm_expected -= take
                if self._ibm_expected == 0:
                    self._dispatch_ibm_highlight()
                continue

            if self._ibm_state == "binary":
                take = min(self._ibm_expected, size - offset)
                self._ibm_binary.extend(data[offset : offset + take])
                offset += take
                self._ibm_expected -= take
                if self._ibm_expected == 0:
                    self._finish_ibm_binary()
                continue

            byte = data[offset]
            offset += 1
            if self._ibm_state == "escape":
                self._begin_ibm_escape(byte)
            elif self._ibm_state == "language-switch":
                self._ibm_state = "ground"
                if byte == ord("@") and self._control.supports_proprinter_switching:
                    self._control.leave_ibm()
                elif byte == _ESC:
                    self._ibm_state = "escape"
            elif self._ibm_state == "bracket":
                self._consume_ibm_bracket(byte)
            elif self._ibm_state == "fixed":
                self._ibm_pending.append(byte)
                if len(self._ibm_pending) == self._ibm_expected:
                    self._dispatch_ibm_fixed()
            elif self._ibm_state == "form-length":
                self._ibm_state = "ground"
                self._mechanism.layout(_PrinterLayoutCommand.IBM_FORM_LENGTH_INCHES, byte)
            elif self._ibm_state == "tab-list":
                if byte == 0 or len(self._ibm_pending) >= self._ibm_expected:
                    self._dispatch_ibm_tabs()
                else:
                    self._ibm_pending.append(byte)
            elif self._ibm_state == "length-header":
                self._ibm_pending.append(byte)
                if len(self._ibm_pending) == 2:
                    count = self._ibm_pending[0] + self._ibm_pending[1] * 256
                    self._ibm_pending.clear()
                    self._ibm_expected = count
                    if self._ibm_command == ord("\\"):
                        self._ibm_state = "verbatim"
                    elif self._ibm_command == ord("@"):
                        self._ibm_state = "bracket-data"
                    elif self._ibm_command in b"=KLYZg":
                        self._ibm_binary.clear()
                        self._ibm_state = "binary"
                    else:
                        self._ibm_state = "discard"
                    if count == 0:
                        self._ibm_state = "ground"
                        if self._ibm_command == ord("="):
                            self._mechanism.font_download(b"")
        return offset

    def _begin_ibm_escape(self, command: int) -> None:
        self._ibm_command = command
        self._ibm_pending.clear()
        if command == ord("%"):
            self._ibm_state = "language-switch"
        elif command == ord("["):
            self._ibm_state = "bracket"
        elif command in b"EFGHORT012467:":
            self._ibm_state = "ground"
            self._dispatch_ibm_no_parameter(command)
        elif command == 0x0E:
            self._ibm_state = "ground"
            self._set_ibm_line_double_width(True)
        elif command == 0x0F:
            self._ibm_state = "ground"
            self._mechanism.layout(_PrinterLayoutCommand.IBM_HORIZONTAL_PITCH, 171)
        elif command == 0x07:
            self._ibm_state = "ground"
            self._mechanism.layout(_PrinterLayoutCommand.IBM_BELL)
        elif command in b"AIJNPQSUW35-_^" or command == ord("C"):
            self._ibm_expected = 1
            self._ibm_state = "fixed"
        elif command == ord("X"):
            self._ibm_expected = 2
            self._ibm_state = "fixed"
        elif command in b"BD":
            self._ibm_expected = 64 if command == ord("B") else 28
            self._ibm_state = "tab-list"
        elif command in b"=KLYZ\\":
            self._ibm_state = "length-header"
        else:
            self._ibm_state = "escape" if command == _ESC else "ground"

    def _dispatch_ibm_no_parameter(self, command: int) -> None:
        if command == ord("E"):
            self._mechanism.rendition = replace(self._mechanism.rendition, bold=True)
        elif command == ord("F"):
            self._mechanism.rendition = replace(self._mechanism.rendition, bold=False)
        elif command == ord("G"):
            self._mechanism.rendition = replace(self._mechanism.rendition, double_strike=True)
        elif command == ord("H"):
            self._mechanism.rendition = replace(self._mechanism.rendition, double_strike=False)
        elif command == ord("O"):
            self._mechanism.layout(_PrinterLayoutCommand.IBM_PERFORATION_SKIP, 0)
        elif command == ord("R"):
            self._mechanism.layout(_PrinterLayoutCommand.IBM_RESET_TABS)
        elif command == ord("T"):
            self._mechanism.rendition = replace(self._mechanism.rendition, script=PrinterScript.NORMAL)
        elif command == ord("0"):
            self._mechanism.layout(_PrinterLayoutCommand.IBM_LINE_SPACING, 27)
        elif command == ord("1"):
            self._mechanism.layout(_PrinterLayoutCommand.IBM_LINE_SPACING, 21)
        elif command == ord("2"):
            self._mechanism.layout(_PrinterLayoutCommand.IBM_LINE_SPACING, self._ibm_pending_line_spacing)
        elif command == ord("4"):
            self._mechanism.layout(_PrinterLayoutCommand.IBM_SET_TOP_OF_FORM)
        elif command == ord("6"):
            self._ibm_character_set = 2
        elif command == ord("7"):
            self._ibm_character_set = 1
        elif command == ord(":"):
            self._mechanism.layout(_PrinterLayoutCommand.IBM_HORIZONTAL_PITCH, 120)

    def _dispatch_ibm_fixed(self) -> None:
        command = self._ibm_command
        parameters = bytes(self._ibm_pending)
        self._ibm_pending.clear()
        self._ibm_state = "ground"
        value = parameters[0]
        if command == ord("A"):
            self._ibm_pending_line_spacing = value * 3
        elif command == ord("C"):
            if value == 0:
                self._ibm_state = "form-length"
            else:
                self._mechanism.layout(_PrinterLayoutCommand.IBM_FORM_LENGTH_LINES, value)
        elif command == ord("I"):
            if value <= 7:
                density = PrinterDensity.DRAFT if value in (0, 1, 4, 5) else PrinterDensity.NEAR_LETTER_QUALITY
                self._mechanism.rendition = replace(self._mechanism.rendition, density=density)
                self._ibm_downloaded_font = value >= 4
                if value in (1, 5):
                    self._mechanism.layout(_PrinterLayoutCommand.IBM_HORIZONTAL_PITCH, 120)
        elif command == ord("J"):
            self._set_ibm_line_double_width(False)
            self._mechanism.layout(_PrinterLayoutCommand.IBM_VERTICAL_MOTION, value)
        elif command == ord("N"):
            self._mechanism.layout(_PrinterLayoutCommand.IBM_PERFORATION_SKIP, value)
        elif command == ord("P") and (enabled := self._ibm_toggle(value)) is not None:
            self._mechanism.proportional_spacing = enabled
        elif command == ord("Q") and value in (3, 22):
            self._ibm_selected = False
        elif command == ord("S") and value in (0, 1):
            self._mechanism.rendition = replace(
                self._mechanism.rendition,
                script=PrinterScript.SUBSCRIPT if value else PrinterScript.SUPERSCRIPT,
            )
        elif command == ord("U") and (enabled := self._ibm_toggle(value)) is not None:
            self._mechanism.direction = PrintDirection.UNIDIRECTIONAL if enabled else PrintDirection.BIDIRECTIONAL
        elif command == ord("W") and (enabled := self._ibm_toggle(value)) is not None:
            self._set_ibm_line_double_width(False)
            self._set_ibm_continuous_double_width(enabled)
        elif command == ord("X"):
            self._mechanism.layout(_PrinterLayoutCommand.HORIZONTAL_MARGINS, *parameters)
        elif command == ord("3"):
            self._mechanism.layout(_PrinterLayoutCommand.IBM_LINE_SPACING, value)
        elif command == ord("5") and (enabled := self._ibm_toggle(value)) is not None:
            self._mechanism.carriage_return_new_line = enabled
        elif command == ord("-") and (enabled := self._ibm_toggle(value)) is not None:
            self._mechanism.rendition = replace(
                self._mechanism.rendition,
                underline=PrinterUnderline.SINGLE if enabled else PrinterUnderline.NONE,
            )
        elif command == ord("_") and (enabled := self._ibm_toggle(value)) is not None:
            self._mechanism.rendition = replace(self._mechanism.rendition, overline=enabled)
        elif command == ord("^"):
            self._mechanism.print_verbatim(parameters)

    def _dispatch_ibm_tabs(self) -> None:
        command = self._ibm_command
        parameters = tuple(self._ibm_pending)
        self._ibm_pending.clear()
        self._ibm_state = "ground"
        self._mechanism.layout(
            _PrinterLayoutCommand.IBM_REPLACE_VERTICAL_TABS
            if command == ord("B")
            else _PrinterLayoutCommand.IBM_REPLACE_HORIZONTAL_TABS,
            *parameters,
        )

    def _consume_ibm_bracket(self, byte: int) -> None:
        self._ibm_pending.append(byte)
        pending = bytes(self._ibm_pending)
        patterns = (b"?58l", b"!p")
        candidates = tuple(pattern for pattern in patterns if pattern.startswith(pending))
        if pending in candidates:
            self._ibm_pending.clear()
            self._ibm_state = "ground"
            if pending == b"?58l" and self._control.supports_proprinter_switching:
                self._control.leave_ibm()
        elif not candidates:
            # Bracketed PPDS commands (double-height, media and unit controls)
            # are framed by a little-endian byte count. Consume their payload
            # now so unsupported binary parameters never leak into text.
            if len(pending) == 1 and byte in _IBM_BRACKET_LENGTH_COMMANDS:
                self._ibm_command = byte
                self._ibm_pending.clear()
                self._ibm_state = "length-header"
            else:
                self._ibm_pending.clear()
                self._ibm_state = "ground"

    def _dispatch_ibm_highlight(self) -> None:
        modes = bytes(self._ibm_pending)
        self._ibm_pending.clear()
        self._ibm_state = "ground"
        if self._ibm_command != ord("@"):
            return
        self._set_ibm_line_double_width(False)
        if len(modes) >= 3:
            spacing = modes[2] >> 4
            height = modes[2] & 0x0F
            if spacing in (1, 2):
                self._mechanism.layout(_PrinterLayoutCommand.IBM_LINE_SPACING, 36 * spacing)
            if height in (1, 2):
                self._ibm_double_height = height == 2
        if len(modes) >= 4:
            width = modes[3] & 0x0F
            if width in (1, 2):
                self._set_ibm_continuous_double_width(width == 2)

    def _finish_ibm_binary(self) -> None:
        command = self._ibm_command
        data = bytes(self._ibm_binary)
        self._ibm_binary.clear()
        self._ibm_state = "ground"
        if command == ord("="):
            self._mechanism.font_download(data)
            return
        if not self._mechanism.accepts_bit_images or not data:
            return
        if command == ord("g"):
            mode = data[0]
            payload = data[1:]
            modes = {
                0: (60, 8, True),
                1: (120, 8, True),
                2: (120, 8, False),
                3: (240, 8, False),
                8: (60, 24, True),
                9: (120, 24, True),
                11: (180, 24, True),
                12: (360, 24, True),
            }
            specification = modes.get(mode)
        else:
            payload = data
            specification = {
                ord("K"): (60, 8, True),
                ord("L"): (120, 8, True),
                ord("Y"): (120, 8, False),
                ord("Z"): (240, 8, False),
            }.get(command)
        if specification is not None and payload:
            self._mechanism.bit_image(*specification, payload)

    @staticmethod
    def _ibm_toggle(value: int) -> bool | None:
        if value in (0, ord("0")):
            return False
        if value in (1, ord("1")):
            return True
        return None

    def _set_ibm_line_double_width(self, enabled: bool) -> None:
        if self._ibm_line_double_width == enabled:
            return
        self._ibm_line_double_width = enabled
        self._mechanism.layout(
            _PrinterLayoutCommand.IBM_DOUBLE_WIDTH,
            int(self._ibm_line_double_width or self._ibm_continuous_double_width),
        )

    def _set_ibm_continuous_double_width(self, enabled: bool) -> None:
        if self._ibm_continuous_double_width == enabled:
            return
        self._ibm_continuous_double_width = enabled
        self._mechanism.layout(
            _PrinterLayoutCommand.IBM_DOUBLE_WIDTH,
            int(self._ibm_line_double_width or self._ibm_continuous_double_width),
        )
