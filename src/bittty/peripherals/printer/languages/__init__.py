"""Printer languages: one decoder per language, driving a shared mechanism.

A new printer language is a new parser module registered with the engine, not
another branch inside one. See docs/peripherals.md.
"""

from __future__ import annotations

from .control import LanguageControl
from .crm import CrmDecoder
from .dec_ppl import DecPplParser
from .engine import _PrinterLanguageEngine
from .mechanism import PrinterMechanism
from .ppds import PpdsParser
from .state import (
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
    _PrinterLayoutCommand,
    _PrinterReportCommand,
)

__all__ = [
    "CrmDecoder",
    "DecPplParser",
    "LanguageControl",
    "PpdsParser",
    "PrintDirection",
    "PrinterCharacterSet",
    "PrinterCharacterState",
    "PrinterColor",
    "PrinterDensity",
    "PrinterLanguage",
    "PrinterMechanism",
    "PrinterRendition",
    "PrinterScript",
    "PrinterUnderline",
    "VirtualPrinterState",
    # Private to the peripheral, but shared across its modules.
    "_PrinterLanguageEngine",
    "_PrinterLayoutCommand",
    "_PrinterReportCommand",
]
