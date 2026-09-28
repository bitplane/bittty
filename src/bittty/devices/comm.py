"""The comm ports' line settings: the host line, and the printer's serial line.

DECSCS, DECSFC, DECSPP and DECSCP name the line they set; a printer selector configures the
printer port, and a comm selector the host line, which a model has with its serial host option.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from ..options import DEC_HOST_LINE
from ..printer_config import PrinterPortSelection
from ..serial_line import (
    BAUD_BY_SELECTOR,
    RATE_BY_SELECTOR,
    SELECTOR_BY_BAUD,
    SELECTOR_BY_RATE,
    FlowControl,
    FlowThreshold,
    HostPortSelection,
    Parity,
    SerialLine,
)
from .base import Device

if TYPE_CHECKING:
    from ..operations import Operation
    from .board import Board

_PRINTER_BAUD = 4800  # the printer line's factory speed
_PRINTER_PARITIES = frozenset({Parity.NONE, Parity.EVEN, Parity.ODD, Parity.MARK, Parity.SPACE})


def _selector(params: tuple[int | None, ...], index: int) -> int:
    """A selector parameter: missing or 0 is the default, 1."""
    return (params[index] if len(params) > index else None) or 1


class CommDevice(Device):
    """Holds the host line's settings and routes line settings to the port they name."""

    def __init__(self, board: Board) -> None:
        self.board = board
        self.line = SerialLine()
        self.has_host_line = DEC_HOST_LINE in board.model.provides
        self.handlers = {
            "DECSCS": self.select_speed,
            "DECSFC": self.select_flow_control,
            "DECSPP": self.set_port_parameters,
            "DECSCP": self.select_ports,
        }
        if self.has_host_line:
            self.handlers["DECSTRL"] = self.set_rate_limit
            board.host.configure(self.line)

    def update(self, **changes) -> None:
        """Change the host line's settings and offer the new line to the connection."""
        if not self.has_host_line:
            return
        line = replace(self.line, **changes)
        if line != self.line:
            self.line = line
            self.board.host.configure(line)

    def select_speed(self, operation: Operation) -> None:
        """DECSCS — host transmit (1) or receive (2), or printer (3); modem speeds are not kept."""
        params = operation.args[0]
        line = _selector(params, 0)
        selector = (params[1] if len(params) > 1 else None) or 0
        if selector and selector not in BAUD_BY_SELECTOR:
            return
        baud = BAUD_BY_SELECTOR.get(selector)  # None: the line's default
        if line == 1:
            self.update(transmit_baud=baud or 9600)
        elif line == 2:
            self.update(receive_baud=baud)  # by default the receive speed follows the transmit speed
        elif line == 3:
            self.board.printer.configure(baud_rate=baud or _PRINTER_BAUD)

    def select_flow_control(self, operation: Operation) -> None:
        """DECSFC — a port's transmit and/or receive flow control, and its threshold."""
        params = operation.args[0]
        port, direction = _selector(params, 0), _selector(params, 1)
        try:
            flow = FlowControl(_selector(params, 2))
            threshold = FlowThreshold(_selector(params, 3))
        except ValueError:
            return
        if port not in (1, 2) or direction not in (1, 2, 3):
            return
        changes = {}
        if direction in (1, 3):
            changes["transmit_flow_control"] = flow
        if direction in (2, 3):
            changes["receive_flow_control"] = flow
        if port == 1:
            self.update(flow_threshold=threshold, **changes)
        else:  # a printer port always uses the low threshold
            self.board.printer.configure(**changes)

    def set_port_parameters(self, operation: Operation) -> None:
        """DECSPP — a port's word size, parity and stop bits."""
        params = operation.args[0]
        port, bits, stop = _selector(params, 0), _selector(params, 1), _selector(params, 3)
        try:
            parity = Parity(_selector(params, 2))
        except ValueError:
            return
        if port not in (1, 2) or bits not in (1, 2) or stop not in (1, 2):
            return
        changes = {"data_bits": 8 if bits == 1 else 7, "parity": parity, "stop_bits": stop}
        if port == 1:
            self.update(**changes)
        elif parity in _PRINTER_PARITIES:
            self.board.printer.configure(**changes)

    def select_ports(self, operation: Operation) -> None:
        """DECSCP — the printer's port and the host session's."""
        params = operation.args[0]
        try:
            printer = PrinterPortSelection(_selector(params, 0))
            host = HostPortSelection(_selector(params, 1))
        except ValueError:
            return
        self.update(port=host)
        self.board.printer.configure(port=printer)

    def set_rate_limit(self, operation: Operation) -> None:
        """DECSTRL — the transmit rate limit for graphic keys (2), function keys (3) or all (1)."""
        params = operation.args[0]
        keys, rate = _selector(params, 0), RATE_BY_SELECTOR.get(_selector(params, 1))
        if rate is None or keys not in (1, 2, 3):
            return
        changes = {}
        if keys in (1, 2):
            changes["transmit_rate_limit"] = rate
        if keys in (1, 3):
            changes["function_key_rate_limit"] = rate
        self.update(**changes)

    def status_strings(self, request: str) -> tuple[str, ...] | None:
        """DECRQSS: restorable settings for each line the request covers, host first."""
        line, printer = self.line, self.board.printer
        host = self.has_host_line
        has_printer = printer.capabilities.configuration
        config = printer.configuration
        strings: list[str] = []
        if request == "*r":
            if host:
                receive = line.receive_baud or line.transmit_baud
                strings += [f"1;{SELECTOR_BY_BAUD[line.transmit_baud]}*r", f"2;{SELECTOR_BY_BAUD[receive]}*r"]
            if has_printer:
                strings.append(f"3;{SELECTOR_BY_BAUD[config.baud_rate]}*r")
        elif request == "*s":
            if host:
                threshold = int(line.flow_threshold)
                strings += [
                    f"1;1;{int(line.transmit_flow_control)};{threshold}*s",
                    f"1;2;{int(line.receive_flow_control)};{threshold}*s",
                ]
            if has_printer:
                strings += [
                    f"2;1;{int(config.transmit_flow_control)};1*s",
                    f"2;2;{int(config.receive_flow_control)};1*s",
                ]
        elif request == "+w":
            for port, settings, on in ((1, line, host), (2, config, has_printer)):
                if on:
                    bits = 1 if settings.data_bits == 8 else 2
                    strings.append(f"{port};{bits};{int(settings.parity)};{settings.stop_bits}+w")
        elif request == "*u" and (host or has_printer):
            strings.append(f"{int(config.port)};{int(line.port)}*u")
        elif request == '"u' and host:
            strings += [
                f'2;{SELECTOR_BY_RATE[line.transmit_rate_limit]}"u',
                f'3;{SELECTOR_BY_RATE[line.function_key_rate_limit]}"u',
            ]
        return tuple(strings) or None
