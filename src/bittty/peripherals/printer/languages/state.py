"""Printer state vocabulary shared by every printer language."""

from __future__ import annotations

from dataclasses import dataclass
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
    IBM_CANCEL_LINE = "ibm-cancel-line"
    IBM_SET_TOP_OF_FORM = "ibm-set-top-of-form"
    IBM_PERFORATION_SKIP = "ibm-perforation-skip"
    IBM_BELL = "ibm-bell"


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
    ibm_downloaded_font: bool = False
