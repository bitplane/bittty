"""Streaming state for the printer languages understood by virtual printers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum


class PrinterLanguage(Enum):
    """Printer command language currently selected by a virtual printer."""

    DEC_PPL = "dec-ppl"
    IBM_PROPRINTER = "ibm-proprinter"


class PrintDirection(Enum):
    """DEC PPL print-direction mode."""

    BIDIRECTIONAL = "bidirectional"
    UNIDIRECTIONAL = "unidirectional"


class PrinterUnderline(Enum):
    """DEC PPL lining selection."""

    NONE = "none"
    SINGLE = "single"
    DOUBLE = "double"


class PrinterScript(Enum):
    """DEC PPL algorithmic script selection."""

    NORMAL = "normal"
    SUPERSCRIPT = "superscript"
    SUBSCRIPT = "subscript"


class PrinterColor(Enum):
    """DEC PPL text colour selection."""

    BLACK = "black"
    RED = "red"
    GREEN = "green"
    YELLOW = "yellow"
    BLUE = "blue"
    MAGENTA = "magenta"
    CYAN = "cyan"
    WHITE = "white"


class PrinterDensity(Enum):
    """DEC PPL font-density selection."""

    DRAFT = "draft"
    LETTER_QUALITY = "letter-quality"
    MEMO = "memo"
    NEAR_LETTER_QUALITY = "near-letter-quality"


@dataclass(frozen=True)
class PrinterRendition:
    """Retained DEC PPL typestyle and algorithmic attributes."""

    typestyle: int = 10
    bold: bool = False
    slanted: bool = False
    underline: PrinterUnderline = PrinterUnderline.NONE
    strikethrough: bool = False
    overline: bool = False
    script: PrinterScript = PrinterScript.NORMAL
    color: PrinterColor = PrinterColor.BLACK
    density: PrinterDensity = PrinterDensity.DRAFT
    double_strike: bool = False

    @property
    def has_lining(self) -> bool:
        """Whether horizontal text motion produces a visible rule."""
        return self.underline is not PrinterUnderline.NONE or self.strikethrough or self.overline


@dataclass(frozen=True)
class PrinterCharacterSet:
    """One designated 94- or 96-character graphic set."""

    size: int
    designator: str

    def __post_init__(self) -> None:
        if self.size not in (94, 96):
            raise ValueError("size must be 94 or 96")
        if not self.designator or not self.designator.isascii():
            raise ValueError("designator must be nonempty ASCII")


_ASCII = PrinterCharacterSet(94, "B")
_USER_PREFERENCE = PrinterCharacterSet(94, "<")
_DEC_SUPPLEMENTAL = PrinterCharacterSet(94, "%5")
_ISO_LATIN_1 = PrinterCharacterSet(96, "A")


@dataclass(frozen=True)
class PrinterCharacterState:
    """DEC PPL graphic-set designation and invocation state."""

    g_sets: tuple[PrinterCharacterSet, PrinterCharacterSet, PrinterCharacterSet, PrinterCharacterSet] = (
        _ASCII,
        _ASCII,
        _USER_PREFERENCE,
        _USER_PREFERENCE,
    )
    gl: int = 0
    gr: int = 2
    single_shift: int | None = None
    user_preference: PrinterCharacterSet = _DEC_SUPPLEMENTAL


class _PrinterLayoutCommand(Enum):
    """Semantic DEC PPL layout operations emitted by the streaming parser."""

    HORIZONTAL_PITCH = "horizontal-pitch"
    VERTICAL_PITCH = "vertical-pitch"
    PAGE_LENGTH = "page-length"
    HORIZONTAL_MARGINS = "horizontal-margins"
    VERTICAL_MARGINS = "vertical-margins"
    HORIZONTAL_ABSOLUTE = "horizontal-absolute"
    HORIZONTAL_RELATIVE = "horizontal-relative"
    VERTICAL_ABSOLUTE = "vertical-absolute"
    VERTICAL_RELATIVE = "vertical-relative"
    SET_HORIZONTAL_TABS = "set-horizontal-tabs"
    SET_VERTICAL_TABS = "set-vertical-tabs"
    CLEAR_TABS = "clear-tabs"
    SET_HORIZONTAL_TAB_HERE = "set-horizontal-tab-here"
    SET_VERTICAL_TAB_HERE = "set-vertical-tab-here"
    CLEAR_HORIZONTAL_TABS = "clear-horizontal-tabs"
    CLEAR_VERTICAL_TABS = "clear-vertical-tabs"
    POSITION_UNIT_MODE = "position-unit-mode"
    IBM_HORIZONTAL_PITCH = "ibm-horizontal-pitch"
    IBM_LINE_SPACING = "ibm-line-spacing"
    IBM_VERTICAL_MOTION = "ibm-vertical-motion"
    IBM_DOUBLE_WIDTH = "ibm-double-width"
    IBM_REPLACE_HORIZONTAL_TABS = "ibm-replace-horizontal-tabs"
    IBM_REPLACE_VERTICAL_TABS = "ibm-replace-vertical-tabs"
    IBM_RESET_TABS = "ibm-reset-tabs"
    IBM_FORM_LENGTH_LINES = "ibm-form-length-lines"
    IBM_FORM_LENGTH_INCHES = "ibm-form-length-inches"
    IBM_LANGUAGE_ENTER = "ibm-language-enter"
    IBM_LANGUAGE_LEAVE = "ibm-language-leave"


class _PrinterReportCommand(Enum):
    """Semantic DEC PPL reports requested by the host."""

    PRIMARY_ATTRIBUTES = "primary-attributes"
    SECONDARY_ATTRIBUTES = "secondary-attributes"
    EXTENDED_STATUS = "extended-status"
    DISABLE_UNSOLICITED_STATUS = "disable-unsolicited-status"
    ENABLE_BRIEF_STATUS = "enable-brief-status"
    ENABLE_EXTENDED_STATUS = "enable-extended-status"
    CURSOR_POSITION = "cursor-position"


@dataclass(frozen=True)
class VirtualPrinterState:
    """Observable language state of a virtual printer."""

    language: PrinterLanguage
    direction: PrintDirection
    proportional_spacing: bool = False
    pitch_from_font: bool = False
    carriage_return_new_line: bool = False
    autowrap: bool = True
    control_representation: bool = False
    line_feed_new_line: bool = False
    position_unit_mode: bool = False
    rendition: PrinterRendition = PrinterRendition()
    characters: PrinterCharacterState = PrinterCharacterState()
    double_width: bool = False
    double_height: bool = False
    ibm_character_set: int = 1
    ibm_code_page: int = 437
    printer_selected: bool = True


_ESC = 0x1B
_CAN = 0x18
_SUB = 0x1A
_C1_CSI = 0x9B
_C1_ST = 0x9C
_C1_STRINGS = frozenset((0x90, 0x98, 0x9D, 0x9E, 0x9F))
_BS = 0x08
_HT = 0x09
_LF = 0x0A
_VT = 0x0B
_FF = 0x0C
_CR = 0x0D
_NEL = 0x85
_HTS = 0x88
_VTS = 0x8A
_SS2 = 0x8E
_SS3 = 0x8F
_SO = 0x0E
_SI = 0x0F
_BASIC_CONTROLS = frozenset((_BS, _HT, _LF, _VT, _FF, _CR))
_DEC_SPECIAL_BYTES = (
    b"\x08",
    b"\x09",
    b"\x0a",
    b"\x0b",
    b"\x0c",
    b"\x0d",
    b"\x0e",
    b"\x0f",
    b"\x1b",
    b"\x85",
    b"\x88",
    b"\x8a",
    b"\x8e",
    b"\x8f",
    b"\x90",
    b"\x98",
    b"\x9b",
    b"\x9d",
    b"\x9e",
    b"\x9f",
)
_NON_PRINTABLE_BYTES = bytes(range(0x20)) + b"\x7f" + bytes(range(0x80, 0xA0))
_MAX_CSI = 128
_IBM_BRACKET_LENGTH_COMMANDS = b"@AFKTZ\\ghim"
_IBM_SPECIAL_BYTES = tuple(
    bytes((byte,))
    for byte in (0x00, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x11, 0x12, 0x13, 0x14, 0x18, 0x1B)
)
_C0_NAMES = (
    "NUL",
    "SOH",
    "STX",
    "ETX",
    "EOT",
    "ENQ",
    "ACK",
    "BEL",
    "BS",
    "HT",
    "LF",
    "VT",
    "FF",
    "CR",
    "SO",
    "SI",
    "DLE",
    "DC1",
    "DC2",
    "DC3",
    "DC4",
    "NAK",
    "SYN",
    "ETB",
    "CAN",
    "EM",
    "SUB",
    "ESC",
    "FS",
    "GS",
    "RS",
    "US",
)
_C1_NAMES = (
    None,
    None,
    "BPH",
    "NBH",
    "IND",
    "NEL",
    "SSA",
    "ESA",
    "HTS",
    "HTJ",
    "VTS",
    "PLD",
    "PLU",
    "RI",
    "SS2",
    "SS3",
    "DCS",
    "PU1",
    "PU2",
    "STS",
    "CCH",
    "MW",
    "SPA",
    "EPA",
    "SOS",
    None,
    "SCI",
    "CSI",
    "ST",
    "OSC",
    "PM",
    "APC",
)


class _PrinterLanguageEngine:
    """Incremental DEC PPL/IBM protocol-selection parser.

    This models retained language modes and resets. Ordinary DEC PPL print data
    remains on a batched fast path to an optional page-assembly sink.
    """

    def __init__(
        self,
        initial_language: PrinterLanguage,
        *,
        supports_proprinter_switching: bool,
        on_printable: Callable[[bytes], None] | None = None,
        on_control: Callable[[int], None] | None = None,
        on_crm_token: Callable[[bytes, str], None] | None = None,
        on_layout: Callable[[_PrinterLayoutCommand, tuple[int, ...]], None] | None = None,
        on_report: Callable[[_PrinterReportCommand], None] | None = None,
        on_reset: Callable[[], None] | None = None,
    ) -> None:
        self._initial_language = initial_language
        self._supports_proprinter_switching = supports_proprinter_switching
        self._on_printable = on_printable
        self._on_control = on_control
        self._on_crm_token = on_crm_token
        self._on_layout = on_layout
        self._on_report = on_report
        self._on_reset = on_reset
        self._language = initial_language
        self._direction = PrintDirection.BIDIRECTIONAL
        self._proportional_spacing = False
        self._pitch_from_font = False
        self._carriage_return_new_line = False
        self._autowrap = True
        self._control_representation = False
        self._line_feed_new_line = False
        self._position_unit_mode = False
        self._rendition = PrinterRendition()
        self._characters = PrinterCharacterState()
        self._dec_state = "ground"
        self._dec_string_is_osc = False
        self._dec_string_kind = 0
        self._dec_string = bytearray()
        self._scs_gset = 0
        self._scs_size = 94
        self._scs_designator = bytearray()
        self._csi = bytearray()
        self._crm_pending = bytearray()
        self._ibm_pending = bytearray()
        self._ibm_state = "ground"
        self._ibm_command = 0
        self._ibm_expected = 0
        self._ibm_pending_line_spacing = 36
        self._ibm_line_double_width = False
        self._ibm_continuous_double_width = False
        self._ibm_double_height = False
        self._ibm_character_set = 1
        self._ibm_code_page = 437
        self._ibm_selected = True
        self._saved_dec_modes: tuple[object, ...] | None = None

    @property
    def state(self) -> VirtualPrinterState:
        return VirtualPrinterState(
            self._language,
            self._direction,
            proportional_spacing=self._proportional_spacing,
            pitch_from_font=self._pitch_from_font,
            carriage_return_new_line=self._carriage_return_new_line,
            autowrap=self._autowrap,
            control_representation=self._control_representation,
            line_feed_new_line=self._line_feed_new_line,
            position_unit_mode=self._position_unit_mode,
            rendition=self._rendition,
            characters=self._characters,
            double_width=(
                self._ibm_line_double_width or self._ibm_continuous_double_width
                if self._language is PrinterLanguage.IBM_PROPRINTER
                else False
            ),
            double_height=self._ibm_double_height if self._language is PrinterLanguage.IBM_PROPRINTER else False,
            ibm_character_set=self._ibm_character_set if self._language is PrinterLanguage.IBM_PROPRINTER else 1,
            ibm_code_page=self._ibm_code_page,
            printer_selected=self._ibm_selected if self._language is PrinterLanguage.IBM_PROPRINTER else True,
        )

    def reset(self) -> None:
        """Apply a power-on reset and discard any partial input sequence."""
        self._language = self._initial_language
        self._reset_dec_modes()
        self._emit_reset()
        self._dec_state = "ground"
        self._dec_string_is_osc = False
        self._dec_string_kind = 0
        self._dec_string.clear()
        self._scs_designator.clear()
        self._csi.clear()
        self._crm_pending.clear()
        self._ibm_pending.clear()
        self._reset_ibm_modes()
        self._saved_dec_modes = None

    def set_ibm_code_page(self, code_page: int) -> None:
        """Apply the code page selected by the physical printer adapter."""
        self._ibm_code_page = int(code_page)

    def feed(self, data: bytes) -> None:
        """Consume one arbitrary stream fragment."""
        offset = 0
        size = len(data)
        while offset < size:
            if self._language is PrinterLanguage.IBM_PROPRINTER:
                offset = self._feed_ibm(data, offset)
            elif self._control_representation:
                offset = self._feed_crm(data, offset)
            else:
                offset = self._feed_dec(data, offset)

    def _feed_dec(self, data: bytes, offset: int) -> int:
        size = len(data)
        while offset < size and self._language is PrinterLanguage.DEC_PPL and not self._control_representation:
            byte = data[offset]
            offset += 1

            if byte in _BASIC_CONTROLS:
                self._emit_control(byte)
            elif byte == _SO:
                self._invoke_gl(1)
            elif byte == _SI:
                self._invoke_gl(0)
            elif byte == _NEL:
                self._csi.clear()
                self._dec_state = "ground"
                self._emit_control(byte)
            elif byte in (_HTS, _VTS):
                self._csi.clear()
                self._dec_state = "ground"
                self._emit_layout(
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
                    self._emit_printable(data[start:next_special])
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
                    self._emit_control(_NEL)
                    self._dec_state = "ground"
                elif byte in (ord("H"), ord("1")):
                    self._emit_layout(_PrinterLayoutCommand.SET_HORIZONTAL_TAB_HERE)
                    self._dec_state = "ground"
                elif byte in (ord("J"), ord("3")):
                    self._emit_layout(_PrinterLayoutCommand.SET_VERTICAL_TAB_HERE)
                    self._dec_state = "ground"
                elif byte == ord("2"):
                    self._emit_layout(_PrinterLayoutCommand.CLEAR_HORIZONTAL_TABS)
                    self._dec_state = "ground"
                elif byte == ord("4"):
                    self._emit_layout(_PrinterLayoutCommand.CLEAR_VERTICAL_TABS)
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
                    self._reset_dec_modes()
                    self._emit_reset()
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
                if byte == ord("=") and self._supports_proprinter_switching:
                    self._enter_ibm_language()
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

    def _emit_printable(self, data: bytes) -> None:
        printable = data.translate(None, _NON_PRINTABLE_BYTES)
        if not printable:
            return
        shifted_index = self._single_shifted_index(printable)
        if shifted_index is None:
            if self._on_printable is not None:
                self._on_printable(printable)
            return
        pending = self._characters
        if shifted_index:
            self._characters = replace(pending, single_shift=None)
            if self._on_printable is not None:
                self._on_printable(printable[:shifted_index])
            self._characters = pending
        if self._on_printable is not None:
            self._on_printable(printable[shifted_index : shifted_index + 1])
        self._characters = replace(pending, single_shift=None)
        if shifted_index + 1 < len(printable) and self._on_printable is not None:
            self._on_printable(printable[shifted_index + 1 :])

    def _emit_verbatim_printable(self, data: bytes) -> None:
        if data and self._on_printable is not None:
            self._on_printable(data)

    def _emit_control(self, byte: int) -> None:
        if self._on_control is not None:
            self._on_control(byte)

    def _emit_layout(self, command: _PrinterLayoutCommand, *parameters: int) -> None:
        if self._on_layout is not None:
            self._on_layout(command, parameters)

    def _emit_report(self, command: _PrinterReportCommand) -> None:
        if self._on_report is not None:
            self._on_report(command)

    def _emit_reset(self) -> None:
        if self._on_reset is not None:
            self._on_reset()

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
        g_sets = list(self._characters.g_sets)
        g_sets[self._scs_gset] = PrinterCharacterSet(self._scs_size, designator)
        self._characters = replace(self._characters, g_sets=tuple(g_sets))

    def _invoke_gl(self, gset: int) -> None:
        self._characters = replace(self._characters, gl=gset)

    def _invoke_gr(self, gset: int) -> None:
        self._characters = replace(self._characters, gr=gset)

    def _single_shift(self, gset: int) -> None:
        self._characters = replace(self._characters, single_shift=gset)

    def _single_shifted_index(self, data: bytes) -> int | None:
        gset = self._characters.single_shift
        if gset is None:
            return None
        is_96 = self._characters.g_sets[gset].size == 96
        return next(
            (
                index
                for index, byte in enumerate(data)
                if byte >= 0xA0 or 0x21 <= byte <= 0x7E or is_96 and byte == 0x20
            ),
            None,
        )

    def _announce_code_extension(self, level: int) -> None:
        g_sets = list(self._characters.g_sets)
        g_sets[0] = _ASCII
        gl = 0
        gr = self._characters.gr
        if level in (1, 2):
            g_sets[1] = _ISO_LATIN_1
            gr = 1
        self._characters = replace(self._characters, g_sets=tuple(g_sets), gl=gl, gr=gr, single_shift=None)

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
        self._characters = replace(
            self._characters,
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
                self._emit_report(
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
                self._emit_report(command)
            return

        if final in (ord("h"), ord("l")):
            private = body.startswith(b"?")
            parameters = self._numeric_parameters(body[1:] if private else body)
            if parameters is None:
                return
            enabled = final == ord("h")
            for parameter in parameters:
                if not private and parameter == 3:
                    self._control_representation = enabled
                elif not private and parameter == 11:
                    self._position_unit_mode = enabled
                    self._emit_layout(_PrinterLayoutCommand.POSITION_UNIT_MODE, int(enabled))
                elif not private and parameter == 20:
                    self._line_feed_new_line = enabled
                elif private and parameter == 7:
                    self._autowrap = enabled
                elif private and parameter == 27:
                    self._proportional_spacing = enabled
                elif private and parameter == 29:
                    self._pitch_from_font = enabled
                elif private and parameter == 40:
                    self._carriage_return_new_line = enabled
                elif private and parameter == 41:
                    self._direction = PrintDirection.UNIDIRECTIONAL if enabled else PrintDirection.BIDIRECTIONAL
                elif private and parameter == 58 and enabled and self._supports_proprinter_switching:
                    self._enter_ibm_language()
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
                self._reset_dec_modes()
                self._emit_reset()
            return

        parameters = self._numeric_parameters_preserving_zeros(body)
        if parameters is None:
            return
        parameter = parameters[0] if parameters else 0
        if final == ord("w"):
            self._emit_layout(_PrinterLayoutCommand.HORIZONTAL_PITCH, parameter)
        elif final == ord("z"):
            self._emit_layout(_PrinterLayoutCommand.VERTICAL_PITCH, parameter)
        elif final == ord("t"):
            self._emit_layout(_PrinterLayoutCommand.PAGE_LENGTH, parameter)
        elif final == ord("s"):
            margins = (parameters + [0, 0])[:2]
            self._emit_layout(_PrinterLayoutCommand.HORIZONTAL_MARGINS, *margins)
        elif final == ord("r"):
            margins = (parameters + [0, 0])[:2]
            self._emit_layout(_PrinterLayoutCommand.VERTICAL_MARGINS, *margins)
        elif final == ord("`"):
            self._emit_layout(_PrinterLayoutCommand.HORIZONTAL_ABSOLUTE, parameter)
        elif final == ord("a"):
            self._emit_layout(_PrinterLayoutCommand.HORIZONTAL_RELATIVE, parameter)
        elif final == ord("d"):
            self._emit_layout(_PrinterLayoutCommand.VERTICAL_ABSOLUTE, parameter)
        elif final == ord("e"):
            self._emit_layout(_PrinterLayoutCommand.VERTICAL_RELATIVE, parameter)
        elif final == ord("u") and body:
            self._emit_layout(_PrinterLayoutCommand.SET_HORIZONTAL_TABS, *parameters[:16])
        elif final == ord("v") and body:
            self._emit_layout(_PrinterLayoutCommand.SET_VERTICAL_TABS, *parameters[:16])
        elif final == ord("g"):
            self._emit_layout(_PrinterLayoutCommand.CLEAR_TABS, *(parameters or [0]))

    def _apply_sgr(self, parameters: list[int], *, private: bool) -> None:
        rendition = self._rendition
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
        self._rendition = rendition

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
            self._rendition = replace(self._rendition, density=density)

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

    def _reset_dec_modes(self) -> None:
        self._direction = PrintDirection.BIDIRECTIONAL
        self._proportional_spacing = False
        self._pitch_from_font = False
        self._carriage_return_new_line = False
        self._autowrap = True
        self._control_representation = False
        self._line_feed_new_line = False
        self._position_unit_mode = False
        self._rendition = PrinterRendition()
        self._characters = PrinterCharacterState()

    def _reset_ibm_modes(self) -> None:
        self._ibm_state = "ground"
        self._ibm_command = 0
        self._ibm_expected = 0
        self._ibm_pending.clear()
        self._ibm_pending_line_spacing = 36
        self._ibm_line_double_width = False
        self._ibm_continuous_double_width = False
        self._ibm_double_height = False
        self._ibm_character_set = 1
        self._ibm_selected = True

    def _feed_crm(self, data: bytes, offset: int) -> int:
        patterns = (b"\x1b[3l", b"\x9b3l")
        size = len(data)
        while offset < size and self._control_representation:
            if not self._crm_pending:
                escape = data.find(b"\x1b", offset)
                csi = data.find(b"\x9b", offset)
                starts = tuple(index for index in (escape, csi) if index != -1)
                if not starts:
                    self._emit_crm_bytes(data[offset:])
                    return size
                start = min(starts)
                self._emit_crm_bytes(data[offset:start])
                offset = start

            self._crm_pending.append(data[offset])
            offset += 1
            pending = bytes(self._crm_pending)
            candidates = tuple(pattern for pattern in patterns if pattern.startswith(pending))
            if not candidates:
                trailing_start = pending[-1] if pending[-1] in (_ESC, _C1_CSI) else None
                self._crm_pending.clear()
                self._emit_crm_bytes(pending[:-1] if trailing_start is not None else pending)
                if trailing_start is not None:
                    self._crm_pending.append(trailing_start)
                continue
            if pending in candidates:
                self._crm_pending.clear()
                if self._on_crm_token is not None:
                    self._on_crm_token(pending, "<CSI>3l")
                self._control_representation = False
        return offset

    def _emit_crm_bytes(self, data: bytes) -> None:
        start = 0
        for offset, byte in enumerate(data):
            if 0x20 <= byte <= 0x7E or byte >= 0xA0:
                continue
            self._emit_printable(data[start:offset])
            if self._on_crm_token is not None:
                self._on_crm_token(bytes((byte,)), self._crm_token(byte))
            if byte in (_LF, _FF):
                self._emit_control(byte)
            start = offset + 1
        self._emit_printable(data[start:])

    @staticmethod
    def _crm_token(byte: int) -> str:
        if byte < 0x20:
            name = _C0_NAMES[byte]
        elif byte == 0x7F:
            name = "DEL"
        else:
            name = _C1_NAMES[byte - 0x80]
        return f"<{name or f'X{byte:02X}'}>"

    def _feed_ibm(self, data: bytes, offset: int) -> int:
        size = len(data)
        while offset < size and self._language is PrinterLanguage.IBM_PROPRINTER:
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
                elif byte in (0x00, 0x07, 0x13):
                    pass
                elif byte in (0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D):
                    if byte in (0x0A, 0x0B, 0x0C, 0x0D):
                        self._set_ibm_line_double_width(False)
                    self._emit_control(byte)
                elif byte == 0x0E:
                    self._set_ibm_line_double_width(True)
                elif byte == 0x0F:
                    self._emit_layout(_PrinterLayoutCommand.IBM_HORIZONTAL_PITCH, 171)
                elif byte == 0x11:
                    self._ibm_selected = True
                elif byte == 0x12:
                    self._emit_layout(_PrinterLayoutCommand.IBM_HORIZONTAL_PITCH, 100)
                elif byte in (0x14, 0x18):
                    self._set_ibm_line_double_width(False)
                else:
                    start = offset - 1
                    next_special = size
                    for marker in _IBM_SPECIAL_BYTES:
                        found = data.find(marker, offset)
                        if found != -1 and found < next_special:
                            next_special = found
                    self._emit_printable(data[start:next_special])
                    offset = next_special
                continue

            if self._ibm_state == "verbatim":
                take = min(self._ibm_expected, size - offset)
                self._emit_verbatim_printable(data[offset : offset + take])
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

            byte = data[offset]
            offset += 1
            if self._ibm_state == "escape":
                self._begin_ibm_escape(byte)
            elif self._ibm_state == "language-switch":
                self._ibm_state = "ground"
                if byte == ord("@") and self._supports_proprinter_switching:
                    self._leave_ibm_language()
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
                self._emit_layout(_PrinterLayoutCommand.IBM_FORM_LENGTH_INCHES, byte)
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
                    else:
                        self._ibm_state = "discard"
                    if count == 0:
                        self._ibm_state = "ground"
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
            self._emit_layout(_PrinterLayoutCommand.IBM_HORIZONTAL_PITCH, 171)
        elif command in b"AIJNPQSUW35-_^" or command == ord("C"):
            self._ibm_expected = 1
            self._ibm_state = "fixed"
        elif command == ord("X"):
            self._ibm_expected = 2
            self._ibm_state = "fixed"
        elif command in b"BD":
            self._ibm_expected = 64 if command == ord("B") else 28
            self._ibm_state = "tab-list"
        elif command in b"KLYZ\\":
            self._ibm_state = "length-header"
        else:
            self._ibm_state = "escape" if command == _ESC else "ground"

    def _dispatch_ibm_no_parameter(self, command: int) -> None:
        if command == ord("E"):
            self._rendition = replace(self._rendition, bold=True)
        elif command == ord("F"):
            self._rendition = replace(self._rendition, bold=False)
        elif command == ord("G"):
            self._rendition = replace(self._rendition, double_strike=True)
        elif command == ord("H"):
            self._rendition = replace(self._rendition, double_strike=False)
        elif command == ord("O"):
            pass  # Perforation skip is retained for the physical-fidelity pass.
        elif command == ord("R"):
            self._emit_layout(_PrinterLayoutCommand.IBM_RESET_TABS)
        elif command == ord("T"):
            self._rendition = replace(self._rendition, script=PrinterScript.NORMAL)
        elif command == ord("0"):
            self._emit_layout(_PrinterLayoutCommand.IBM_LINE_SPACING, 27)
        elif command == ord("1"):
            self._emit_layout(_PrinterLayoutCommand.IBM_LINE_SPACING, 21)
        elif command == ord("2"):
            self._emit_layout(_PrinterLayoutCommand.IBM_LINE_SPACING, self._ibm_pending_line_spacing)
        elif command == ord("4"):
            pass  # The page snapshot has a fixed physical origin.
        elif command == ord("6"):
            self._ibm_character_set = 2
        elif command == ord("7"):
            self._ibm_character_set = 1
        elif command == ord(":"):
            self._emit_layout(_PrinterLayoutCommand.IBM_HORIZONTAL_PITCH, 120)

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
                self._emit_layout(_PrinterLayoutCommand.IBM_FORM_LENGTH_LINES, value)
        elif command == ord("I"):
            if value <= 7:
                density = PrinterDensity.DRAFT if value in (0, 1, 4, 5) else PrinterDensity.NEAR_LETTER_QUALITY
                self._rendition = replace(self._rendition, density=density)
                if value in (1, 5):
                    self._emit_layout(_PrinterLayoutCommand.IBM_HORIZONTAL_PITCH, 120)
        elif command == ord("J"):
            self._set_ibm_line_double_width(False)
            self._emit_layout(_PrinterLayoutCommand.IBM_VERTICAL_MOTION, value)
        elif command == ord("N"):
            pass  # Perforation skip is retained for the physical-fidelity pass.
        elif command == ord("P") and (enabled := self._ibm_toggle(value)) is not None:
            self._proportional_spacing = enabled
        elif command == ord("Q") and value in (3, 22):
            self._ibm_selected = False
        elif command == ord("S") and value in (0, 1):
            self._rendition = replace(
                self._rendition,
                script=PrinterScript.SUBSCRIPT if value else PrinterScript.SUPERSCRIPT,
            )
        elif command == ord("U") and (enabled := self._ibm_toggle(value)) is not None:
            self._direction = PrintDirection.UNIDIRECTIONAL if enabled else PrintDirection.BIDIRECTIONAL
        elif command == ord("W") and (enabled := self._ibm_toggle(value)) is not None:
            self._set_ibm_line_double_width(False)
            self._set_ibm_continuous_double_width(enabled)
        elif command == ord("X"):
            self._emit_layout(_PrinterLayoutCommand.HORIZONTAL_MARGINS, *parameters)
        elif command == ord("3"):
            self._emit_layout(_PrinterLayoutCommand.IBM_LINE_SPACING, value)
        elif command == ord("5") and (enabled := self._ibm_toggle(value)) is not None:
            self._carriage_return_new_line = enabled
        elif command == ord("-") and (enabled := self._ibm_toggle(value)) is not None:
            self._rendition = replace(
                self._rendition,
                underline=PrinterUnderline.SINGLE if enabled else PrinterUnderline.NONE,
            )
        elif command == ord("_") and (enabled := self._ibm_toggle(value)) is not None:
            self._rendition = replace(self._rendition, overline=enabled)
        elif command == ord("^"):
            self._emit_verbatim_printable(parameters)

    def _dispatch_ibm_tabs(self) -> None:
        command = self._ibm_command
        parameters = tuple(self._ibm_pending)
        self._ibm_pending.clear()
        self._ibm_state = "ground"
        self._emit_layout(
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
            if pending == b"?58l" and self._supports_proprinter_switching:
                self._leave_ibm_language()
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
                self._emit_layout(_PrinterLayoutCommand.IBM_LINE_SPACING, 36 * spacing)
            if height in (1, 2):
                self._ibm_double_height = height == 2
        if len(modes) >= 4:
            width = modes[3] & 0x0F
            if width in (1, 2):
                self._set_ibm_continuous_double_width(width == 2)

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
        self._emit_layout(
            _PrinterLayoutCommand.IBM_DOUBLE_WIDTH,
            int(self._ibm_line_double_width or self._ibm_continuous_double_width),
        )

    def _set_ibm_continuous_double_width(self, enabled: bool) -> None:
        if self._ibm_continuous_double_width == enabled:
            return
        self._ibm_continuous_double_width = enabled
        self._emit_layout(
            _PrinterLayoutCommand.IBM_DOUBLE_WIDTH,
            int(self._ibm_line_double_width or self._ibm_continuous_double_width),
        )

    def _enter_ibm_language(self) -> None:
        if self._language is PrinterLanguage.IBM_PROPRINTER:
            return
        self._saved_dec_modes = (
            self._direction,
            self._proportional_spacing,
            self._pitch_from_font,
            self._carriage_return_new_line,
            self._autowrap,
            self._control_representation,
            self._line_feed_new_line,
            self._position_unit_mode,
            self._rendition,
            self._characters,
        )
        self._reset_ibm_modes()
        self._emit_layout(_PrinterLayoutCommand.IBM_LANGUAGE_ENTER)
        self._language = PrinterLanguage.IBM_PROPRINTER

    def _leave_ibm_language(self) -> None:
        if self._language is not PrinterLanguage.IBM_PROPRINTER:
            return
        self._emit_layout(_PrinterLayoutCommand.IBM_LANGUAGE_LEAVE)
        if self._saved_dec_modes is not None:
            (
                self._direction,
                self._proportional_spacing,
                self._pitch_from_font,
                self._carriage_return_new_line,
                self._autowrap,
                self._control_representation,
                self._line_feed_new_line,
                self._position_unit_mode,
                self._rendition,
                self._characters,
            ) = self._saved_dec_modes
        self._saved_dec_modes = None
        self._language = PrinterLanguage.DEC_PPL
        self._dec_state = "ground"
