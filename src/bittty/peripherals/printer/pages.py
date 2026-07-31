"""Physical page geometry and immutable virtual-printer page snapshots."""

from __future__ import annotations

from dataclasses import dataclass

from .languages import VirtualPrinterState

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
class PrinterRenditionSpan(PrinterPageItem):
    """A lined horizontal movement produced by HPA or HPR."""

    state: VirtualPrinterState

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.bounds.width <= 0 or self.bounds.height <= 0:
            raise ValueError("bounds must have positive width and height")
        if not isinstance(self.state, VirtualPrinterState):
            raise TypeError("state must be a VirtualPrinterState")


@dataclass(frozen=True)
class PrinterBitImage(PrinterPageItem):
    """Packed vertical slices emitted by an IBM PPDS bit-image command."""

    data: bytes
    horizontal_dpi: int
    vertical_dpi: int
    pins: int
    adjacent_dots: bool
    state: VirtualPrinterState

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.data, bytes) or not self.data:
            raise ValueError("data must be nonempty bytes")
        for name in ("horizontal_dpi", "vertical_dpi", "pins"):
            _require_int(name, getattr(self, name))
        if self.horizontal_dpi <= 0 or self.vertical_dpi <= 0:
            raise ValueError("image density must be positive")
        if self.pins not in (8, 24):
            raise ValueError("pins must be 8 or 24")
        if len(self.data) % (self.pins // 8):
            raise ValueError("data must contain complete vertical slices")
        if not isinstance(self.adjacent_dots, bool):
            raise TypeError("adjacent_dots must be a boolean")
        if not isinstance(self.state, VirtualPrinterState):
            raise TypeError("state must be a VirtualPrinterState")
        columns = len(self.data) // (self.pins // 8)
        expected_width = columns * PRINT_UNITS_PER_INCH // self.horizontal_dpi
        expected_height = self.pins * PRINT_UNITS_PER_INCH // self.vertical_dpi
        if self.bounds.width != expected_width or self.bounds.height != expected_height:
            raise ValueError("bounds must match packed image dimensions and density")


@dataclass(frozen=True)
class PrinterDownloadedGlyph:
    """One retained 9-pin IBM downloadable character definition."""

    code_point: int
    attributes: bytes
    columns: bytes

    def __post_init__(self) -> None:
        _require_int("code_point", self.code_point)
        if not 0 <= self.code_point <= 255:
            raise ValueError("code_point must be from 0 to 255")
        if not isinstance(self.attributes, bytes) or len(self.attributes) != 2:
            raise ValueError("attributes must contain exactly two bytes")
        if not isinstance(self.columns, bytes) or len(self.columns) != 11:
            raise ValueError("columns must contain exactly eleven bytes")


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
        self._current_marks: list[bool] = []
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
        self._current_marks.append(marks)
        self._marked = self._marked or marks

    def checkpoint(self) -> int:
        """Return a token that can roll back subsequently appended page items."""
        return len(self._current_items)

    def truncate(self, checkpoint: int) -> None:
        """Discard items appended after a checkpoint on the current page."""
        _require_int("checkpoint", checkpoint)
        if not 0 <= checkpoint <= len(self._current_items):
            raise ValueError("checkpoint is not on the current page")
        del self._current_items[checkpoint:]
        del self._current_marks[checkpoint:]
        self._marked = any(self._current_marks)

    def complete(self, *, force: bool = False) -> PrinterPage | None:
        """Complete the current page, optionally including a blank page."""
        if not force and not self._marked:
            return None
        page = self.current_page
        self._completed.append(page)
        self._current_number += 1
        self._current_items = []
        self._current_marks = []
        self._marked = False
        return page

    def take_completed_pages(self) -> tuple[PrinterPage, ...]:
        pages = tuple(self._completed)
        self._completed.clear()
        return pages
