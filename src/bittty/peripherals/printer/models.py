"""Printer models: the printer's equivalent of the terminal's Model.

A PrinterModel is a printer's physical identity and report repertoire as data. The
virtual printer simulates whichever one it is given.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...connections.printer_config import PrinterType
from .pages import LETTER_PAGE_GEOMETRY, PRINT_UNITS_PER_INCH, PrinterPageGeometry, PrinterRect


@dataclass(frozen=True)
class PrinterModel:
    """Immutable physical identity and report capabilities of a virtual printer.

    Device-attribute tuples contain the parameters following ``CSI ?`` (DA) or
    ``CSI >`` (DA2).  Status tuples contain DEC PPL extended-report parameters;
    the virtual printer supplies the private CSI marker and the brief report.
    ``None`` means the model does not implement that report.
    """

    name: str
    device_type: PrinterType = PrinterType.DEC_ANSI
    page_geometry: PrinterPageGeometry = LETTER_PAGE_GEOMETRY
    primary_device_attributes: tuple[int, ...] | None = (72,)
    secondary_device_attributes: tuple[int, ...] | None = None
    ready_status_parameters: tuple[int, ...] = (20,)
    offline_status_parameters: tuple[int, ...] = (24,)
    unavailable_status_parameters: tuple[int, ...] = (59,)
    supports_cursor_position_report: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("profile name must not be empty")
        object.__setattr__(self, "device_type", PrinterType(self.device_type))
        for field_name in (
            "primary_device_attributes",
            "secondary_device_attributes",
            "ready_status_parameters",
            "offline_status_parameters",
            "unavailable_status_parameters",
        ):
            parameters = getattr(self, field_name)
            if parameters is None:
                if field_name.endswith("status_parameters"):
                    raise ValueError(f"{field_name} must contain one or more parameters from 0 to 999")
                continue
            parameters = tuple(parameters)
            if not parameters or any(parameter < 0 or parameter > 999 for parameter in parameters):
                raise ValueError(f"{field_name} must contain one or more parameters from 0 to 999")
            object.__setattr__(self, field_name, parameters)


GENERIC_DEC_PPL2_PRINTER = PrinterModel("generic-dec-ppl2")
GENERIC_PROPRINTER = PrinterModel(
    "generic-ibm-proprinter",
    device_type=PrinterType.PROPRINTER,
    primary_device_attributes=None,
)
GENERIC_DEC_AND_IBM_PRINTER = PrinterModel(
    "generic-dec-ppl2-and-ibm-proprinter",
    device_type=PrinterType.DEC_AND_IBM,
)


DEFAULT_MODELS = {
    PrinterType.DEC_ANSI: GENERIC_DEC_PPL2_PRINTER,
    PrinterType.PROPRINTER: GENERIC_PROPRINTER,
    PrinterType.DEC_AND_IBM: GENERIC_DEC_AND_IBM_PRINTER,
}


# Terminals & Printers Handbook ch. 14: "ESC [ c or ESC [ 0 c — LA120 transmits ESC [ ? 2 c",
# on fanfold paper up to 14 7/8 inches wide; the form length here is the usual 11 inches.
_FANFOLD = PrinterPageGeometry(
    width=PRINT_UNITS_PER_INCH * 119 // 8,
    height=PRINT_UNITS_PER_INCH * 11,
    printable_area=PrinterRect(0, 0, PRINT_UNITS_PER_INCH * 119 // 8, PRINT_UNITS_PER_INCH * 11),
)
LA120 = PrinterModel("la120", page_geometry=_FANFOLD, primary_device_attributes=(2,))
