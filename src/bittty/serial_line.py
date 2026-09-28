"""Serial line settings: what a VT510 comm port is set to, whatever is on the cable.

The host line and the printer's serial line share their vocabulary (the DECSCS, DECSFC and
DECSPP selectors); the terminal holds each line's settings and offers them to a connection
that can apply them. Defaults are the VT510's factory Set-Up.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

# DECSCS speed selectors; 0 (or none) is the line's own default.
BAUD_BY_SELECTOR = {
    1: 300,
    2: 600,
    3: 1200,
    4: 2400,
    5: 4800,
    6: 9600,
    7: 19200,
    8: 38400,
    9: 57600,
    10: 76800,
    11: 115200,
}
SELECTOR_BY_BAUD = {baud: selector for selector, baud in BAUD_BY_SELECTOR.items()}
# DECSTRL rate selectors, in characters per second
RATE_BY_SELECTOR = {1: 150, 2: 50, 3: 30}
SELECTOR_BY_RATE = {rate: selector for selector, rate in RATE_BY_SELECTOR.items()}


class HostPortSelection(IntEnum):
    """The connector the host session uses (DECSCP Ps2)."""

    COMM1 = 1  # RS232, 25-pin
    COMM2 = 2  # MMJ


class Parity(IntEnum):
    """Parity selectors used by DECSPP. Printers support the checked parities only."""

    NONE = 1
    EVEN = 2
    ODD = 3
    EVEN_UNCHECKED = 4
    ODD_UNCHECKED = 5
    MARK = 6
    SPACE = 7


class FlowControl(IntEnum):
    """Flow-control selectors used by DECSFC."""

    XON_XOFF = 1
    DTR = 2
    BOTH = 3
    NONE = 4


class FlowThreshold(IntEnum):
    """Receive-flow threshold: 64 or 768 characters."""

    LOW = 1
    HIGH = 2


@dataclass(frozen=True)
class SerialLine:
    """The host line's settings and its communication modes (DECXRLM, DECMCM, DECHDPXM)."""

    port: HostPortSelection = HostPortSelection.COMM1
    transmit_baud: int = 9600
    receive_baud: int | None = None  # None: the receive speed follows the transmit speed
    data_bits: int = 8
    parity: Parity = Parity.NONE
    stop_bits: int = 1
    transmit_flow_control: FlowControl = FlowControl.NONE
    receive_flow_control: FlowControl = FlowControl.XON_XOFF
    flow_threshold: FlowThreshold = FlowThreshold.LOW
    transmit_rate_limit: int = 150  # characters per second, for graphic keys (DECSTRL)
    function_key_rate_limit: int = 150
    rate_limited: bool = False  # DECXRLM
    modem_control: bool = False  # DECMCM
    half_duplex: bool = False  # DECHDPXM
