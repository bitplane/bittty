"""DEC PPL decoder."""

from __future__ import annotations

from dataclasses import replace

from ._bytes import (
    _BASIC_CONTROLS,
    _C1_CSI,
    _C1_ST,
    _C1_STRINGS,
    _CAN,
    _DEC_SPECIAL_BYTES,
    _ESC,
    _HTS,
    _MAX_CSI,
    _NEL,
    _SI,
    _SO,
    _SS2,
    _SS3,
    _SUB,
    _VTS,
)
from .control import LanguageControl
from .mechanism import PrinterMechanism
from .state import (
    _ASCII,
    _ISO_LATIN_1,
    PrintDirection,
    PrinterCharacterSet,
    PrinterColor,
    PrinterDensity,
    PrinterLanguage,
    PrinterRendition,
    PrinterScript,
    PrinterUnderline,
    _PrinterLayoutCommand,
    _PrinterReportCommand,
)


class DecPplParser:
    """DEC PPL decoder: C0/C1 controls, CSI, DCS, SCS and SGR driving the mechanism."""

    def __init__(self, mechanism: PrinterMechanism, control: LanguageControl) -> None:
        self._mechanism = mechanism
        self._control = control
        self._scs_gset = 0
        self._scs_size = 94
        self._dec_string = bytearray()
        self._scs_designator = bytearray()
        self._csi = bytearray()
        self.reset()

    def reset(self) -> None:
        """Return to ground, discarding any partial sequence."""
        self._dec_state = "ground"
        self._dec_string_is_osc = False
        self._dec_string_kind = 0
        self._dec_string.clear()
        self._scs_designator.clear()
        self._csi.clear()

    def feed(self, data: bytes, offset: int) -> int:
        size = len(data)
        while (
            offset < size
            and self._control.language is PrinterLanguage.DEC_PPL
            and not self._mechanism.control_representation
        ):
            byte = data[offset]
            offset += 1

            if byte in _BASIC_CONTROLS:
                self._mechanism.control(byte)
            elif byte == _SO:
                self._invoke_gl(1)
            elif byte == _SI:
                self._invoke_gl(0)
            elif byte == _NEL:
                self._csi.clear()
                self._dec_state = "ground"
                self._mechanism.control(byte)
            elif byte in (_HTS, _VTS):
                self._csi.clear()
                self._dec_state = "ground"
                self._mechanism.layout(
                    _PrinterLayoutCommand.SET_HORIZONTAL_TAB_HERE
                    if byte == _HTS
                    else _PrinterLayoutCommand.SET_VERTICAL_TAB_HERE
                )
            elif byte in (_SS2, _SS3):
                self._csi.clear()
                self._dec_state = "ground"
                self._single_shift(2 if byte == _SS2 else 3)
            elif self._dec_state == "ground":
                if byte == _ESC:
                    self._dec_state = "escape"
                elif byte == _C1_CSI:
                    self._begin_csi()
                elif byte in _C1_STRINGS:
                    self._begin_string(byte)
                else:
                    # Most printer output is ordinary text. Scan it in C rather
                    # than returning to Python for every byte.
                    start = offset - 1
                    next_special = size
                    for marker in _DEC_SPECIAL_BYTES:
                        found = data.find(marker, offset)
                        if found != -1 and found < next_special:
                            next_special = found
                    self._mechanism.print(data[start:next_special])
                    offset = next_special
            elif self._dec_state == "escape":
                if byte == ord("["):
                    self._begin_csi()
                elif byte in (ord("P"), ord("X"), ord("]"), ord("^"), ord("_")):
                    self._begin_string(byte + 0x40)
                elif byte in (ord("("), ord(")"), ord("*"), ord("+")):
                    self._begin_scs(byte - ord("("), size=94)
                elif byte in (ord("-"), ord("."), ord("/")):
                    self._begin_scs(byte - ord("-") + 1, size=96)
                elif byte == ord(" "):
                    self._dec_state = "escape_space"
                elif byte == ord("%"):
                    self._dec_state = "percent"
                elif byte == ord("E"):
                    self._mechanism.control(_NEL)
                    self._dec_state = "ground"
                elif byte in (ord("H"), ord("1")):
                    self._mechanism.layout(_PrinterLayoutCommand.SET_HORIZONTAL_TAB_HERE)
                    self._dec_state = "ground"
                elif byte in (ord("J"), ord("3")):
                    self._mechanism.layout(_PrinterLayoutCommand.SET_VERTICAL_TAB_HERE)
                    self._dec_state = "ground"
                elif byte == ord("2"):
                    self._mechanism.layout(_PrinterLayoutCommand.CLEAR_HORIZONTAL_TABS)
                    self._dec_state = "ground"
                elif byte == ord("4"):
                    self._mechanism.layout(_PrinterLayoutCommand.CLEAR_VERTICAL_TABS)
                    self._dec_state = "ground"
                elif byte in (ord("N"), ord("O")):
                    self._single_shift(2 if byte == ord("N") else 3)
                    self._dec_state = "ground"
                elif byte in (ord("n"), ord("o")):
                    self._invoke_gl(2 if byte == ord("n") else 3)
                    self._dec_state = "ground"
                elif byte in (ord("~"), ord("}"), ord("|")):
                    self._invoke_gr({ord("~"): 1, ord("}"): 2, ord("|"): 3}[byte])
                    self._dec_state = "ground"
                elif byte == ord("c"):
                    self._mechanism.reset_modes()
                    self._mechanism.power_on_reset()
                    self._dec_state = "ground"
                elif byte == _ESC:
                    pass
                else:
                    self._dec_state = "ground"
            elif self._dec_state == "escape_space":
                if byte in (ord("L"), ord("M"), ord("N")):
                    self._announce_code_extension(byte - ord("K"))
                    self._dec_state = "ground"
                elif byte == _ESC:
                    self._dec_state = "escape"
                else:
                    self._dec_state = "ground"
            elif self._dec_state == "scs":
                if 0x20 <= byte <= 0x2F and len(self._scs_designator) < 8:
                    self._scs_designator.append(byte)
                elif 0x30 <= byte <= 0x7E:
                    self._scs_designator.append(byte)
                    self._designate_character_set()
                    self._dec_state = "ground"
                elif byte == _ESC:
                    self._scs_designator.clear()
                    self._dec_state = "escape"
                elif byte in (_CAN, _SUB):
                    self._scs_designator.clear()
                    self._dec_state = "ground"
                else:
                    self._scs_designator.clear()
                    self._dec_state = "ground"
            elif self._dec_state == "percent":
                if byte == ord("=") and self._control.supports_proprinter_switching:
                    self._control.enter_ibm()
                    self._dec_state = "ground"
                elif byte == _ESC:
                    self._dec_state = "escape"
                else:
                    self._dec_state = "ground"
            elif self._dec_state == "csi":
                self._consume_csi(byte)
            elif self._dec_state == "string":
                if byte == _C1_ST or byte in (_CAN, _SUB) or (byte == 0x07 and self._dec_string_is_osc):
                    self._end_string(dispatch=byte not in (_CAN, _SUB))
                elif byte == _ESC:
                    self._dec_state = "string_escape"
                elif self._dec_string_kind == 0x90 and len(self._dec_string) < _MAX_CSI:
                    self._dec_string.append(byte)
            else:  # string_escape
                if byte in (ord("\\"), _C1_ST, _CAN, _SUB) or byte == 0x07 and self._dec_string_is_osc:
                    self._end_string(dispatch=byte not in (_CAN, _SUB))
                elif byte != _ESC:
                    self._dec_state = "string"
        return offset

    def _begin_csi(self) -> None:
        self._csi.clear()
        self._dec_state = "csi"

    def _begin_string(self, kind: int) -> None:
        self._dec_string_kind = kind
        self._dec_string_is_osc = kind == 0x9D
        self._dec_string.clear()
        self._dec_state = "string"

    def _end_string(self, *, dispatch: bool) -> None:
        if dispatch and self._dec_string_kind == 0x90:
            self._dispatch_dcs(bytes(self._dec_string))
        self._dec_string.clear()
        self._dec_string_kind = 0
        self._dec_state = "ground"

    def _begin_scs(self, gset: int, *, size: int) -> None:
        self._scs_gset = gset
        self._scs_size = size
        self._scs_designator.clear()
        self._dec_state = "scs"

    def _designate_character_set(self) -> None:
        designator = self._scs_designator.decode("ascii")
        self._scs_designator.clear()
        g_sets = list(self._mechanism.characters.g_sets)
        g_sets[self._scs_gset] = PrinterCharacterSet(self._scs_size, designator)
        self._mechanism.characters = replace(self._mechanism.characters, g_sets=tuple(g_sets))

    def _invoke_gl(self, gset: int) -> None:
        self._mechanism.characters = replace(self._mechanism.characters, gl=gset)

    def _invoke_gr(self, gset: int) -> None:
        self._mechanism.characters = replace(self._mechanism.characters, gr=gset)

    def _single_shift(self, gset: int) -> None:
        self._mechanism.characters = replace(self._mechanism.characters, single_shift=gset)

    def _announce_code_extension(self, level: int) -> None:
        g_sets = list(self._mechanism.characters.g_sets)
        g_sets[0] = _ASCII
        gl = 0
        gr = self._mechanism.characters.gr
        if level in (1, 2):
            g_sets[1] = _ISO_LATIN_1
            gr = 1
        self._mechanism.characters = replace(
            self._mechanism.characters, g_sets=tuple(g_sets), gl=gl, gr=gr, single_shift=None
        )

    def _dispatch_dcs(self, data: bytes) -> None:
        marker = data.find(b"!u")
        if marker == -1:
            return
        parameters = self._numeric_parameters(data[:marker])
        designator = data[marker + 2 :]
        if parameters is None or len(parameters) > 1 or not designator or not designator.isascii():
            return
        size_parameter = parameters[0] if parameters else 0
        if size_parameter not in (0, 1):
            return
        self._mechanism.characters = replace(
            self._mechanism.characters,
            user_preference=PrinterCharacterSet(94 if size_parameter == 0 else 96, designator.decode("ascii")),
        )

    def _consume_csi(self, byte: int) -> None:
        if byte in (_CAN, _SUB):
            self._csi.clear()
            self._dec_state = "ground"
            return
        if byte == _ESC:
            self._csi.clear()
            self._dec_state = "escape"
            return
        if 0x40 <= byte <= 0x7E:
            body = bytes(self._csi)
            self._csi.clear()
            self._dec_state = "ground"
            self._dispatch_dec_csi(body, byte)
            return
        if len(self._csi) >= _MAX_CSI:
            self._csi.clear()
            self._dec_state = "ground"
            return
        self._csi.append(byte)

    def _dispatch_dec_csi(self, body: bytes, final: int) -> None:
        if final == ord("c"):
            secondary = body.startswith(b">")
            parameters = self._numeric_parameters(body[1:] if secondary else body)
            if parameters is not None and (not parameters or parameters == [0]):
                self._mechanism.report(
                    _PrinterReportCommand.SECONDARY_ATTRIBUTES
                    if secondary
                    else _PrinterReportCommand.PRIMARY_ATTRIBUTES
                )
            return

        if final == ord("n"):
            private = body.startswith(b"?")
            parameters = self._numeric_parameters(body[1:] if private else body)
            if parameters is None or len(parameters) > 1:
                return
            parameter = parameters[0] if parameters else 0
            if private:
                command = {
                    1: _PrinterReportCommand.DISABLE_UNSOLICITED_STATUS,
                    2: _PrinterReportCommand.ENABLE_BRIEF_STATUS,
                    3: _PrinterReportCommand.ENABLE_EXTENDED_STATUS,
                }.get(parameter)
            else:
                command = {
                    0: _PrinterReportCommand.EXTENDED_STATUS,
                    5: _PrinterReportCommand.EXTENDED_STATUS,
                    6: _PrinterReportCommand.CURSOR_POSITION,
                }.get(parameter)
            if command is not None:
                self._mechanism.report(command)
            return

        if final in (ord("h"), ord("l")):
            private = body.startswith(b"?")
            parameters = self._numeric_parameters(body[1:] if private else body)
            if parameters is None:
                return
            enabled = final == ord("h")
            for parameter in parameters:
                if not private and parameter == 3:
                    self._mechanism.control_representation = enabled
                elif not private and parameter == 11:
                    self._mechanism.position_unit_mode = enabled
                    self._mechanism.layout(_PrinterLayoutCommand.POSITION_UNIT_MODE, int(enabled))
                elif not private and parameter == 20:
                    self._mechanism.line_feed_new_line = enabled
                elif private and parameter == 7:
                    self._mechanism.autowrap = enabled
                elif private and parameter == 27:
                    self._mechanism.proportional_spacing = enabled
                elif private and parameter == 29:
                    self._mechanism.pitch_from_font = enabled
                elif private and parameter == 40:
                    self._mechanism.carriage_return_new_line = enabled
                elif private and parameter == 41:
                    self._mechanism.direction = (
                        PrintDirection.UNIDIRECTIONAL if enabled else PrintDirection.BIDIRECTIONAL
                    )
                elif private and parameter == 58 and enabled and self._control.supports_proprinter_switching:
                    self._control.enter_ibm()
                    return
            return

        if final == ord("m"):
            private = body.startswith(b"?")
            parameters = self._numeric_parameters_preserving_zeros(body[1:] if private else body)
            if parameters is not None:
                self._apply_sgr(parameters or [0], private=private)
            return

        if final == ord("z") and body.endswith(b'"'):
            parameters = self._numeric_parameters(body[:-1])
            if parameters is not None:
                self._apply_density(parameters[0] if parameters else 0)
            return

        if final == ord("p") and body.endswith(b"!"):
            parameters = self._numeric_parameters(body[:-1])
            if parameters is not None:
                self._mechanism.reset_modes()
                self._mechanism.power_on_reset()
            return

        parameters = self._numeric_parameters_preserving_zeros(body)
        if parameters is None:
            return
        parameter = parameters[0] if parameters else 0
        if final == ord("w"):
            self._mechanism.layout(_PrinterLayoutCommand.HORIZONTAL_PITCH, parameter)
        elif final == ord("z"):
            self._mechanism.layout(_PrinterLayoutCommand.VERTICAL_PITCH, parameter)
        elif final == ord("t"):
            self._mechanism.layout(_PrinterLayoutCommand.PAGE_LENGTH, parameter)
        elif final == ord("s"):
            margins = (parameters + [0, 0])[:2]
            self._mechanism.layout(_PrinterLayoutCommand.HORIZONTAL_MARGINS, *margins)
        elif final == ord("r"):
            margins = (parameters + [0, 0])[:2]
            self._mechanism.layout(_PrinterLayoutCommand.VERTICAL_MARGINS, *margins)
        elif final == ord("`"):
            self._mechanism.layout(_PrinterLayoutCommand.HORIZONTAL_ABSOLUTE, parameter)
        elif final == ord("a"):
            self._mechanism.layout(_PrinterLayoutCommand.HORIZONTAL_RELATIVE, parameter)
        elif final == ord("d"):
            self._mechanism.layout(_PrinterLayoutCommand.VERTICAL_ABSOLUTE, parameter)
        elif final == ord("e"):
            self._mechanism.layout(_PrinterLayoutCommand.VERTICAL_RELATIVE, parameter)
        elif final == ord("u") and body:
            self._mechanism.layout(_PrinterLayoutCommand.SET_HORIZONTAL_TABS, *parameters[:16])
        elif final == ord("v") and body:
            self._mechanism.layout(_PrinterLayoutCommand.SET_VERTICAL_TABS, *parameters[:16])
        elif final == ord("g"):
            self._mechanism.layout(_PrinterLayoutCommand.CLEAR_TABS, *(parameters or [0]))

    def _apply_sgr(self, parameters: list[int], *, private: bool) -> None:
        rendition = self._mechanism.rendition
        for parameter in parameters:
            if private:
                if parameter == 0:
                    rendition = replace(
                        rendition,
                        overline=False,
                        script=PrinterScript.NORMAL,
                    )
                elif parameter == 4:
                    rendition = replace(rendition, script=PrinterScript.SUPERSCRIPT)
                elif parameter == 5:
                    rendition = replace(rendition, script=PrinterScript.SUBSCRIPT)
                elif parameter == 6:
                    rendition = replace(rendition, overline=True)
                elif parameter == 24:
                    rendition = replace(rendition, script=PrinterScript.NORMAL)
                elif parameter == 26:
                    rendition = replace(rendition, overline=False)
                continue

            if parameter == 0:
                rendition = PrinterRendition(
                    typestyle=rendition.typestyle,
                    density=rendition.density,
                )
            elif parameter == 1:
                rendition = replace(rendition, bold=True)
            elif parameter == 3:
                rendition = replace(rendition, slanted=True)
            elif parameter == 4:
                rendition = replace(rendition, underline=PrinterUnderline.SINGLE)
            elif parameter == 9:
                rendition = replace(rendition, strikethrough=True)
            elif 10 <= parameter <= 19:
                rendition = replace(rendition, typestyle=parameter)
            elif parameter == 21:
                rendition = replace(rendition, underline=PrinterUnderline.DOUBLE)
            elif parameter == 22:
                rendition = replace(rendition, bold=False)
            elif parameter == 23:
                rendition = replace(rendition, slanted=False)
            elif parameter == 24:
                rendition = replace(rendition, underline=PrinterUnderline.NONE)
            elif parameter == 29:
                rendition = replace(rendition, strikethrough=False)
            elif 30 <= parameter <= 37:
                rendition = replace(rendition, color=tuple(PrinterColor)[parameter - 30])
            elif parameter == 39:
                rendition = replace(rendition, color=PrinterColor.BLACK)
            elif parameter == 53:
                rendition = replace(rendition, overline=True)
            elif parameter == 55:
                rendition = replace(rendition, overline=False)
        self._mechanism.rendition = rendition

    def _apply_density(self, parameter: int) -> None:
        densities = {
            0: PrinterDensity.DRAFT,
            1: PrinterDensity.DRAFT,
            2: PrinterDensity.LETTER_QUALITY,
            3: PrinterDensity.MEMO,
            4: PrinterDensity.NEAR_LETTER_QUALITY,
        }
        density = densities.get(parameter)
        if density is not None:
            self._mechanism.rendition = replace(self._mechanism.rendition, density=density)

    @staticmethod
    def _numeric_parameters(data: bytes) -> list[int] | None:
        if any(byte not in b"0123456789;" for byte in data):
            return None
        if not data:
            return []
        return [int(part) for part in data.split(b";") if part]

    @staticmethod
    def _numeric_parameters_preserving_zeros(data: bytes) -> list[int] | None:
        if any(byte not in b"0123456789;" for byte in data):
            return None
        if not data:
            return []
        return [int(part) if part else 0 for part in data.split(b";")]
