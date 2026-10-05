"""Virtual printers: the far end of the board's auxiliary printer cable, and the hardcopy
terminal, a printer on the host line.

The only public entry to this package. Module internals (`languages`, `pages`)
are not part of the API.
"""

from __future__ import annotations

from .hardcopy import HardcopyTerminal
from .languages import (
    PrintDirection,
    PrinterCharacterSet,
    PrinterCharacterState,
    PrinterColor,
    PrinterDensity,
    PrinterLanguage,
    PrinterRendition,
    PrinterScript,
    PrinterUnderline,
    VirtualPrinterState,
)
from .models import (
    GENERIC_DEC_AND_IBM_PRINTER,
    GENERIC_DEC_PPL2_PRINTER,
    GENERIC_PROPRINTER,
    LA120,
    PrinterModel,
)
from .pages import (
    LETTER_PAGE_GEOMETRY,
    PRINT_UNITS_PER_INCH,
    PrinterBitImage,
    PrinterControlToken,
    PrinterDownloadedGlyph,
    PrinterPage,
    PrinterPageGeometry,
    PrinterPageItem,
    PrinterRect,
    PrinterRenditionSpan,
    PrinterTextRun,
)
from .virtual import (
    PrinterMechanicalAction,
    PrinterMechanicalEvent,
    PrinterUnsolicitedReports,
    VirtualPrinter,
)

__all__ = [
    "GENERIC_DEC_AND_IBM_PRINTER",
    "GENERIC_DEC_PPL2_PRINTER",
    "GENERIC_PROPRINTER",
    "HardcopyTerminal",
    "LA120",
    "LETTER_PAGE_GEOMETRY",
    "PRINT_UNITS_PER_INCH",
    "PrintDirection",
    "PrinterBitImage",
    "PrinterCharacterSet",
    "PrinterCharacterState",
    "PrinterColor",
    "PrinterControlToken",
    "PrinterDensity",
    "PrinterDownloadedGlyph",
    "PrinterLanguage",
    "PrinterMechanicalAction",
    "PrinterMechanicalEvent",
    "PrinterModel",
    "PrinterPage",
    "PrinterPageGeometry",
    "PrinterPageItem",
    "PrinterRect",
    "PrinterRendition",
    "PrinterRenditionSpan",
    "PrinterScript",
    "PrinterTextRun",
    "PrinterUnderline",
    "PrinterUnsolicitedReports",
    "VirtualPrinter",
    "VirtualPrinterState",
]
