"""Physical page geometry and immutable virtual-printer page snapshots."""

from __future__ import annotations

from dataclasses import dataclass

from .printer_languages import VirtualPrinterState

PRINT_UNITS_PER_INCH = 21_600


def _require_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")


@dataclass(frozen=True)
class PrinterRect:
    """A half-open rectangle in physical printer units."""

    left: int
    top: int
    right: int
    bottom: int

    def __post_init__(self) -> None:
        for name in ("left", "top", "right", "bottom"):
            _require_int(name, getattr(self, name))
        if self.right < self.left:
            raise ValueError("right must not be less than left")
        if self.bottom < self.top:
            raise ValueError("bottom must not be less than top")

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


@dataclass(frozen=True)
class PrinterPageGeometry:
    """Physical sheet dimensions and the device's printable area."""

    width: int
    height: int
    printable_area: PrinterRect

    def __post_init__(self) -> None:
        _require_int("width", self.width)
        _require_int("height", self.height)
        if self.width <= 0:
            raise ValueError("width must be positive")
        if self.height <= 0:
            raise ValueError("height must be positive")
        if not isinstance(self.printable_area, PrinterRect):
            raise TypeError("printable_area must be a PrinterRect")
        if (
            self.printable_area.left < 0
            or self.printable_area.top < 0
            or self.printable_area.right > self.width
            or self.printable_area.bottom > self.height
        ):
            raise ValueError("printable_area must be contained within the sheet")


LETTER_PAGE_GEOMETRY = PrinterPageGeometry(
    width=PRINT_UNITS_PER_INCH * 17 // 2,
    height=PRINT_UNITS_PER_INCH * 11,
    printable_area=PrinterRect(
        0,
        0,
        PRINT_UNITS_PER_INCH * 17 // 2,
        PRINT_UNITS_PER_INCH * 11,
    ),
)


@dataclass(frozen=True)
class PrinterPageItem:
    """Base record for one mark in a printer page's display list."""

    bounds: PrinterRect

    def __post_init__(self) -> None:
        if not isinstance(self.bounds, PrinterRect):
            raise TypeError("bounds must be a PrinterRect")


@dataclass(frozen=True)
class PrinterTextRun(PrinterPageItem):
    """One positioned run of printable source bytes."""

    data: bytes
    text: str | None
    advance: int
    state: VirtualPrinterState

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.data, bytes):
            raise TypeError("data must be bytes")
        if not self.data:
            raise ValueError("data must not be empty")
        if self.text is not None:
            if not isinstance(self.text, str):
                raise TypeError("text must be a string or None")
            if not self.data.isascii() or self.text != self.data.decode("ascii"):
                raise ValueError("text must be the exact ASCII decoding of data")
        _require_int("advance", self.advance)
        if self.advance <= 0:
            raise ValueError("advance must be positive")
        if self.bounds.width != self.advance:
            raise ValueError("bounds width must equal advance")
        if self.bounds.height <= 0:
            raise ValueError("bounds height must be positive")
        if not isinstance(self.state, VirtualPrinterState):
            raise TypeError("state must be a VirtualPrinterState")


@dataclass(frozen=True)
class PrinterControlToken(PrinterPageItem):
    """One positioned CRM graphic token."""

    source: bytes
    text: str
    advance: int
    state: VirtualPrinterState

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.source, bytes):
            raise TypeError("source must be bytes")
        if not self.source:
            raise ValueError("source must not be empty")
        if not isinstance(self.text, str):
            raise TypeError("text must be a string")
        if not self.text or not self.text.isascii():
            raise ValueError("text must be nonempty ASCII")
        _require_int("advance", self.advance)
        if self.advance <= 0:
            raise ValueError("advance must be positive")
        if self.bounds.width != self.advance:
            raise ValueError("bounds width must equal advance")
        if self.bounds.height <= 0:
            raise ValueError("bounds height must be positive")
        if not isinstance(self.state, VirtualPrinterState):
            raise TypeError("state must be a VirtualPrinterState")


@dataclass(frozen=True)
class PrinterPage:
    """An immutable physical-page display-list snapshot."""

    number: int
    geometry: PrinterPageGeometry
    items: tuple[PrinterPageItem, ...] = ()

    def __post_init__(self) -> None:
        _require_int("number", self.number)
        if self.number <= 0:
            raise ValueError("number must be positive")
        if not isinstance(self.geometry, PrinterPageGeometry):
            raise TypeError("geometry must be a PrinterPageGeometry")
        if not isinstance(self.items, tuple):
            raise TypeError("items must be a tuple")
        if not all(isinstance(item, PrinterPageItem) for item in self.items):
            raise TypeError("items must contain PrinterPageItem records")


class _PrinterPageStore:
    """Single-writer mutable storage behind immutable public page snapshots."""

    def __init__(self, geometry: PrinterPageGeometry) -> None:
        if not isinstance(geometry, PrinterPageGeometry):
            raise TypeError("geometry must be a PrinterPageGeometry")
        self._geometry = geometry
        self._current_number = 1
        self._current_items: list[PrinterPageItem] = []
        self._marked = False
        self._completed: list[PrinterPage] = []

    @property
    def geometry(self) -> PrinterPageGeometry:
        return self._geometry

    @property
    def current_page(self) -> PrinterPage:
        return PrinterPage(
            self._current_number,
            self._geometry,
            tuple(self._current_items),
        )

    @property
    def completed_pages(self) -> tuple[PrinterPage, ...]:
        return tuple(self._completed)

    def append(self, item: PrinterPageItem, *, marks: bool = True) -> None:
        if not isinstance(item, PrinterPageItem):
            raise TypeError("item must be a PrinterPageItem")
        self._current_items.append(item)
        self._marked = self._marked or marks

    def complete(self, *, force: bool = False) -> PrinterPage | None:
        """Complete the current page, optionally including a blank page."""
        if not force and not self._marked:
            return None
        page = self.current_page
        self._completed.append(page)
        self._current_number += 1
        self._current_items = []
        self._marked = False
        return page

    def take_completed_pages(self) -> tuple[PrinterPage, ...]:
        pages = tuple(self._completed)
        self._completed.clear()
        return pages
