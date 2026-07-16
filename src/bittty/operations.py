"""Parser operation model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from . import constants


@dataclass(frozen=True)
class Operation:
    """A parsed terminal operation."""

    name: str
    args: tuple[Any, ...] = field(default_factory=tuple)
    raw: str = ""


class OperationSink(Protocol):
    """Receives operations emitted by the parser."""

    def handle_operation(self, operation: Operation) -> None:
        """Handle one parsed operation."""


CONTROL_NAMES = {
    constants.ENQ: "C0_ENQ",
    constants.BEL: "C0_BEL",
    constants.BS: "C0_BS",
    constants.HT: "C0_HT",
    constants.LF: "C0_LF",
    constants.VT: "C0_VT",
    constants.FF: "C0_FF",
    constants.CR: "C0_CR",
    constants.SO: "C0_SO",
    constants.SI: "C0_SI",
    constants.DEL: "C0_DEL",
}


def control_name(ch: str) -> str:
    """Return a stable operation name for a C0 control character."""
    return CONTROL_NAMES.get(ch, f"C0_{ord(ch):02X}")
