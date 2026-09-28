"""Charset operation handler for the current board state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..charsets import CHARSETS, NATIONAL_CHARSET_DESIGNATORS, SUPPLEMENTAL_SETS, get_charset
from ..operations import Operation
from ..options import DEC_UPSS
from .base import Device

if TYPE_CHECKING:
    from .board import Board


class CharsetDevice(Device):
    """Owns charset state and applies charset operations."""

    def __init__(self, board: Board) -> None:
        self.board = board
        self.g0_charset = "B"
        self.g1_charset = "B"
        self.g2_charset = "B"
        self.g3_charset = "B"
        self.current_charset = 0  # G-set invoked into GL (0x20-0x7F); SI/SO/LS2/LS3 move it
        self.gr = 2  # G-set invoked into GR (0xA0-0xFF), G2 at power-on; LS1R/LS2R/LS3R move it
        self.single_shift: int | None = None
        self.cache = {}
        self.charset_array = ["B", "B", "B", "B"]
        # What "<" designates: the user-preferred supplemental set (DEC Supplemental on a VT220).
        self.preferred = board.model.upss or "%5"
        self.handlers = {
            "SS2": lambda op: self.single_shift_2(),
            "SS3": lambda op: self.single_shift_3(),
            "LS2": lambda op: self.locking_shift(2),
            "LS3": lambda op: self.locking_shift(3),
            "LS1R": lambda op: self.locking_shift(1, right=True),
            "LS2R": lambda op: self.locking_shift(2, right=True),
            "LS3R": lambda op: self.locking_shift(3, right=True),
            "SCS_G0": lambda op: self.designate(0, op.args[0]),
            "SCS_G1": lambda op: self.designate(1, op.args[0]),
            "SCS_G2": lambda op: self.designate(2, op.args[0]),
            "SCS_G3": lambda op: self.designate(3, op.args[0]),
        }
        if board.model.upss is not None:
            self.handlers["DECRQUPSS"] = lambda op: board.host.write(f"\x1bP0!u{self.preferred}\x1b\\", flush=True)
        if DEC_UPSS in board.model.provides:
            self.handlers["DECAUPSS"] = self.assign_preferred

    def _recognizes(self, designator: str) -> bool:
        """Whether this is a set bittty has and the model's charset repertoire includes it."""
        charsets = self.board.model.charsets
        return (designator in CHARSETS or designator == "<") and (charsets is None or designator in charsets)

    def assign_preferred(self, operation: Operation) -> None:
        """DECAUPSS — make a supplemental set the one "<" designates; any other is ignored."""
        if operation.args in SUPPLEMENTAL_SETS:
            self.preferred = operation.args[1]
            self.cache.pop("<", None)

    def designate(self, index: int, designator: str) -> None:
        """Apply an SCS G-set designation, ignoring charsets the terminal lacks."""
        if not self._recognizes(designator):
            return
        if (
            designator in NATIONAL_CHARSET_DESIGNATORS
            and self.board.modes.recognizes(True, 42)
            and not self.board.modes.national_charset_mode
        ):
            return
        setters = (self.set_g0_charset, self.set_g1_charset, self.set_g2_charset, self.set_g3_charset)
        setters[index](designator)

    def translate(self, text: str) -> str:
        """Translate text through the invoked G-sets: GL for 0x20-0x7F, GR for 0xA0-0xFF."""
        if not text:
            return text
        # Fast path: nothing pending and both halves are ASCII -> passthrough.
        if (
            self.single_shift is None
            and self.charset_array[self.current_charset] == "B"
            and self.charset_array[self.gr] == "B"
        ):
            return text
        return "".join(self._translate_char(char) for char in text)

    def _translate_char(self, char: str) -> str:
        """Translate one character through the G-set currently invoked for its half."""
        if self.single_shift is not None:  # SS2/SS3 designate the next single character
            designator = self.charset_array[self.single_shift]
            self.single_shift = None
            key = char
        elif 0xA0 <= ord(char) <= 0xFF:  # GR: right half maps through the GR-invoked set
            designator = self.charset_array[self.gr]
            key = chr(ord(char) - 0x80)
        else:  # GL: left half maps through the GL-invoked set
            designator = self.charset_array[self.current_charset]
            key = char
        if designator == "B":
            return char
        return self._get_charset_map(designator).get(key, char)

    def _get_charset_map(self, charset_designator: str):
        if charset_designator not in self.cache:
            self.cache[charset_designator] = get_charset(
                self.preferred if charset_designator == "<" else charset_designator
            )
        return self.cache[charset_designator]

    def set_g0_charset(self, charset: str) -> None:
        """Set the G0 character set."""
        self.g0_charset = charset
        self.charset_array[0] = charset

    def set_g1_charset(self, charset: str) -> None:
        """Set the G1 character set."""
        self.g1_charset = charset
        self.charset_array[1] = charset

    def set_g2_charset(self, charset: str) -> None:
        """Set the G2 character set."""
        self.g2_charset = charset
        self.charset_array[2] = charset

    def set_g3_charset(self, charset: str) -> None:
        """Set the G3 character set."""
        self.g3_charset = charset
        self.charset_array[3] = charset

    def shift_in(self) -> None:
        """Shift In (SI / LS0) - invoke G0 into GL."""
        self.current_charset = 0

    def shift_out(self) -> None:
        """Shift Out (SO / LS1) - invoke G1 into GL."""
        self.current_charset = 1

    def locking_shift(self, gset: int, right: bool = False) -> None:
        """Persistently invoke a G-set: LS2/LS3 into GL, LS1R/LS2R/LS3R into GR."""
        if right:
            self.gr = gset
        else:
            self.current_charset = gset

    def single_shift_2(self) -> None:
        """Single Shift 2 (SS2) - use G2 for next character only."""
        self.single_shift = 2

    def single_shift_3(self) -> None:
        """Single Shift 3 (SS3) - use G3 for next character only."""
        self.single_shift = 3

    def save(self) -> tuple:
        """GL, GR and the G0-G3 designations, for DECSC."""
        return self.current_charset, self.gr, tuple(self.charset_array)

    def restore(self, saved: tuple) -> None:
        """Reinstate what save() returned (DECRC)."""
        self.current_charset, self.gr, designations = saved
        setters = (self.set_g0_charset, self.set_g1_charset, self.set_g2_charset, self.set_g3_charset)
        for setter, designation in zip(setters, designations):
            setter(designation)

    def reset(self) -> None:
        """Reset charset selections to US ASCII."""
        self.set_g0_charset("B")
        self.set_g1_charset("B")
        self.set_g2_charset("B")
        self.set_g3_charset("B")
        self.current_charset = 0
        self.gr = 2
        self.single_shift = None
