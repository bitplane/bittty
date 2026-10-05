"""Printer port configuration: what the terminal has been told is attached.

Tier 2 of the peripheral model (see docs/peripherals.md). The terminal holds this
whether or not anything is on the cable — DECSPRTT, DECSDPT and DECSPPCS set it, as do
DECSCP, DECSCS, DECSFC and DECSPP when they name the printer (devices/comm.py), and
DECRQSS reports it back. It is offered to a
connected adapter through the printer port; what the adapter does with it is the
peripheral's business.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from .serial_line import FlowControl, FlowThreshold, Parity


class PrinterPortSelection(IntEnum):
    """Physical VT510 printer-port selection."""

    PARALLEL = 1
    COMM1 = 2
    COMM2 = 3


class PrinterType(IntEnum):
    """Physical printer language capability."""

    DEC_ANSI = 1
    PROPRINTER = 2
    DEC_AND_IBM = 3


class PrintedDataType(IntEnum):
    """Character repertoire emitted by the terminal."""

    NATIONAL = 1
    NATIONAL_LINE_DRAWING = 2
    MULTINATIONAL = 3
    ALL = 4


class ProPrinterCodePage(IntEnum):
    """IBM ProPrinter code pages accepted by DECSPPCS."""

    GREEK = 210
    SPANISH = 220
    PC_INTERNATIONAL = 437
    MULTILINGUAL = 850
    SLAVIC = 852
    TURKISH = 857
    PORTUGUESE = 860
    HEBREW = 862
    FRENCH_CANADIAN = 863
    DANISH = 865
    CYRILLIC = 866


@dataclass(frozen=True)
class PrinterConfiguration:
    """Complete physical printer configuration exposed to an adapter."""

    port: PrinterPortSelection = PrinterPortSelection.PARALLEL
    printer_type: PrinterType = PrinterType.DEC_ANSI
    printed_data_type: PrintedDataType = PrintedDataType.NATIONAL
    code_page: ProPrinterCodePage = ProPrinterCodePage.PC_INTERNATIONAL
    baud_rate: int = 4800
    data_bits: int = 8
    parity: Parity = Parity.NONE
    stop_bits: int = 1
    transmit_flow_control: FlowControl = FlowControl.XON_XOFF
    receive_flow_control: FlowControl = FlowControl.XON_XOFF
    flow_threshold: FlowThreshold = FlowThreshold.LOW
    ignore_null: bool = False
