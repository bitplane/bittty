"""Installed hardware options: what a terminal *is*, as opposed to what is plugged in.

Tier 1 of the peripheral model (see docs/peripherals.md). An option is a board, a
port or a ROM fitted at power-on — the Advanced Video Option in a VT100, the
printer port on a VT220. It decides the terminal's mode repertoire and what it
answers to Device Attributes.

The distinction that matters, and the one real hardware draws: **an option
enables modes; a connection does not.** A VT220 honours DECPFF and answers
DECSPRTT with nothing on the end of the cable, because the port is what the
terminal has. Whether a printer is actually attached only changes the status it
reports. So options live here, configuration lives in printer_config.py, and
what is on the far end lives in peripherals/.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .connections import PrinterStatus
from .mode_profiles import PRINTER_PORT_MODE_CAPABILITIES


@dataclass(frozen=True)
class PrinterCapabilities:
    """Printer protocol repertoire a printer port implements."""

    media_copy: bool = True
    configuration: bool = True
    disconnected_status: PrinterStatus = PrinterStatus.OFFLINE


NO_PRINTER = PrinterCapabilities(media_copy=False, configuration=False)


# Capabilities that are not modes. A control function is either implemented or
# not recognised at all, so these gate whether a device registers its handlers
# rather than what a mode table resolves to. They come from an installed option
# (the locator port) or from the model's own software (the kitty protocol).
DEC_LOCATOR = "dec.locator"
KITTY_KEYBOARD = "kitty.keyboard"


@dataclass(frozen=True)
class Option:
    """One hardware option installed in a terminal.

    Options compose by union: a model's active repertoire is its own capability
    set plus everything its options contribute.
    """

    name: str
    mode_capabilities: frozenset[str] = field(default_factory=frozenset)
    provides: frozenset[str] = field(default_factory=frozenset)
    printer: PrinterCapabilities | None = None


# --- printer ports --------------------------------------------------------- #
# Every DEC terminal from the VT100's EIA auxiliary port onward had one; no
# software emulator does, except xterm's print-to-pipe fiction.

DEC_PRINTER_PORT = Option(
    "dec-printer-port",
    mode_capabilities=PRINTER_PORT_MODE_CAPABILITIES,
    printer=PrinterCapabilities(configuration=False),
)

VT510_PRINTER_PORT = Option(
    "vt510-printer-port",
    mode_capabilities=PRINTER_PORT_MODE_CAPABILITIES,
    printer=PrinterCapabilities(),
)

XTERM_PRINTER_PIPE = Option(
    "xterm-printer-pipe",
    mode_capabilities=PRINTER_PORT_MODE_CAPABILITIES,
    printer=PrinterCapabilities(configuration=False, disconnected_status=PrinterStatus.NOT_READY),
)


# --- locator port ---------------------------------------------------------- #
# DEC shipped two locator devices on one micro-DIN port: the VSXXX-AA mouse and
# the VSXXX-AB graphics tablet (VT330/VT340). The port is what enables DECELR
# and friends; whether a device is on the end of it only changes the report.

LOCATOR_PORT = Option("locator-port", provides=frozenset({DEC_LOCATOR}))
