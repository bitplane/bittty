"""Scrollback: the lines a terminal keeps after they scroll off the top of the board.

A store holds logical lines (rows joined back up across automatic wraps), numbered
from 0 for its whole life, so a number stays a stable reference to a line however
much is evicted or cleared before it. It lays them out at whatever width is asked
of it, so history re-wraps when the venue resizes. A line takes ceil(width / columns)
rows, and an empty line one, where a line's width is its cells, counted twice on a
double-width or double-height line (DECDWL/DECDHL, whose halves are two lines). The
row count is a function of that one number, so any store (in memory, or a file of
logs indexed by width) lays history out alike.

Rows arrive one at a time, saying whether the line goes on in the next row. A line
still arriving is held open, its head in history and its tail on the screen.

Search, indexes and persistence are further protocols a store may also implement;
`Scrollback` is the least every store does.
"""

from __future__ import annotations

from array import array
from bisect import bisect_right
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import chain
from operator import itemgetter
from typing import Protocol

from ..constants import LINE_SINGLE
from ..style import Style
from ..video import CONTINUATION, Cell, WideHead

DEFAULT_MAX_CELLS = 2_000_000  # about 10,000 lines of 200 cells
# Widths a memory store keeps row counts for. Untested on purpose: forgetting a width
# changes nothing a view shows, but every append updates each width kept, and dragging
# a window's edge would otherwise leave dozens behind.
_VIEWED_WIDTHS = 4
_STYLE, _CHAR = itemgetter(0), itemgetter(1)
_UNSTYLED = Style()


@dataclass(frozen=True, slots=True)
class ScrollbackLine:
    """One logical line, as text and styles rather than cells.

    `text` is what the line says: each cell's characters, with a wide glyph's tail
    cell holding none. `styles` holds each cell's style, shared objects rather than
    one (style, char) pair per cell. `shape` is the number of code points in each
    cell (0 for a wide glyph's tail), or None when every cell holds exactly one.
    `attribute` is the line's size (DECSWL/DECDWL/DECDHL), as video keeps it.
    """

    text: str
    styles: tuple[Style, ...]
    shape: tuple[int, ...] | None = None
    attribute: str = LINE_SINGLE

    @classmethod
    def of(cls, cells: Sequence[Cell], trim: bool = False, attribute: str = LINE_SINGLE) -> ScrollbackLine:
        """Compact a row of video cells; `trim` drops its trailing unstyled blanks, as at a line's end."""
        chars = tuple(map(_CHAR, cells))
        text = "".join(chars)
        if trim:
            cut = _content_end(cells, text)
            text = text[: len(text) - len(cells) + cut]
            cells, chars = cells[:cut], chars[:cut]
        regular = len(text) == len(chars) and CONTINUATION not in chars
        return cls(text, tuple(map(_STYLE, cells)), None if regular else tuple(map(len, chars)), attribute)

    @classmethod
    def join(cls, parts: Sequence[ScrollbackLine]) -> ScrollbackLine:
        """One line from the rows it was wrapped across, the size of its first."""
        regular = all(part.shape is None for part in parts)
        shape = None if regular else tuple(chain.from_iterable(part.shape or (1,) * len(part) for part in parts))
        text = "".join(part.text for part in parts)
        return cls(text, tuple(chain.from_iterable(part.styles for part in parts)), shape, parts[0].attribute)

    def __len__(self) -> int:
        """Cells."""
        return len(self.styles)

    @property
    def scale(self) -> int:
        """Columns each cell takes: two on a double-width or double-height line."""
        return 1 if self.attribute == LINE_SINGLE else 2

    @property
    def width(self) -> int:
        """Columns the line takes."""
        return len(self.styles) * self.scale

    @property
    def runs(self) -> list[tuple[int, Style]]:
        """(first cell, style) for each stretch of one style."""
        styles = self.styles
        return [(x, style) for x, style in enumerate(styles) if not x or style != styles[x - 1]]

    def cells(self, start: int, stop: int) -> list[Cell]:
        """Cells start to stop, a wide glyph cut by either end blanked in its style."""
        styles = self.styles[start:stop]
        if self.shape is None:
            return list(zip(styles, self.text[start:stop]))
        shape = self.shape
        offset = sum(shape[:start])
        stop = start + len(styles)
        cells = []
        for x, style in enumerate(styles, start):
            char = self.text[offset : offset + shape[x]]
            offset += shape[x]
            if x + 1 < len(shape) and shape[x + 1] == 0:
                char = WideHead(char) if x + 1 < stop else " "
            elif shape[x] == 0 and x == start:
                char = " "
            cells.append((style, char))
        return cells


def _content_end(cells: Sequence[Cell], text: str) -> int:
    """Where a row's trailing blanks in the default style begin."""
    cut = len(cells)
    floor = cut - len(text) + len(text.rstrip(" "))  # where the trailing spaces start
    if floor < cut and cells[floor:].count(cells[-1]) == cut - floor and cells[-1][0] == _UNSTYLED:
        return floor  # the usual case, the page's one blank cell: one comparison
    while cut > floor and cells[cut - 1][0] == _UNSTYLED:
        cut -= 1
    return cut


def rows_of(width: int, columns: int) -> int:
    """The rows a line `width` columns wide takes at `columns`: an empty line takes one."""
    return max(1, -(-width // columns))


class ScrollbackView(Protocol):
    """A store's lines laid out at one width: a sequence of rows, the oldest first."""

    def __len__(self) -> int: ...
    def __getitem__(self, row: int) -> list[Cell]:
        """The cells of a row that lie wholly in it: as many as fill its columns, half that on a
        double-size line, a cell or wide glyph cut by its edge blank."""
        ...

    def line_at(self, row: int) -> tuple[int, int]:
        """(line number, row within that line) of a row."""
        ...

    def row_for(self, line: int) -> int:
        """The first row of a line."""
        ...


class Scrollback(Protocol):
    """Where a terminal keeps the lines that scrolled off the board."""

    first: int  # the oldest line held

    @property
    def end(self) -> int:
        """One past the newest line held, counting one still arriving."""
        ...

    def append(self, row: ScrollbackLine, wrapped: bool = False) -> None:
        """Take the next row; `wrapped` says its line goes on in the row after."""
        ...

    def clear(self) -> None:
        """Forget every line (ED 3); numbering carries on."""
        ...

    def line(self, number: int) -> ScrollbackLine:
        """A held line, first <= number < end; one still arriving as far as it has."""
        ...

    def width(self, columns: int) -> ScrollbackView:
        """The lines laid out at `columns`."""
        ...


class MemoryScrollback:
    """A Scrollback in memory, the oldest lines forgotten past a budget of cells.

    Each line costs its cells plus one, so empty lines are bounded too. A line too
    long for the whole budget keeps its newest rows.
    """

    def __init__(self, max_cells: int = DEFAULT_MAX_CELLS) -> None:
        self.max_cells = max_cells
        self.first = 0
        self.cells = 0  # the cost of everything held
        self._lines: deque[ScrollbackLine] = deque()  # complete lines, numbered from first
        self._open: deque[ScrollbackLine] = deque()  # the rows held of the line still arriving
        self._open_width = 0  # the columns of the rows held of the open line
        self._joined: ScrollbackLine | None = None  # the open line's rows joined, until the next arrives
        # Per width viewed: rows before each complete line, from line _base on.
        self._base = 0
        self._rows: dict[int, array] = {}

    @property
    def end(self) -> int:
        return self.first + len(self._lines) + bool(self._open)

    def append(self, row: ScrollbackLine, wrapped: bool = False) -> None:
        self._open.append(row)
        self._open_width += row.width
        self.cells += len(row.styles)
        self._joined = None
        if not wrapped:
            self._complete()
        self._evict()

    def clear(self) -> None:
        self.first = self.end
        self.cells = self._open_width = 0
        self._lines.clear()
        self._open.clear()
        self._joined = None
        self._base = self.first
        self._rows = {columns: array("q", [0]) for columns in self._rows}

    def width(self, columns: int) -> MemoryView:
        return MemoryView(self, columns)

    def row_counts(self, columns: int) -> array:
        """Rows before each complete line at `columns`, from line `_base` on; counted when first asked."""
        if columns not in self._rows:
            if len(self._rows) == _VIEWED_WIDTHS:
                del self._rows[next(iter(self._rows))]
            rows = array("q", bytes(8 * (self.first - self._base + 1)))
            for line in self._lines:
                rows.append(rows[-1] + rows_of(line.width, columns))
            self._rows[columns] = rows
        return self._rows[columns]

    def line(self, number: int) -> ScrollbackLine:
        """A held line; the open one as far as it has arrived."""
        complete = self.first + len(self._lines)
        if number < complete:
            return self._lines[number - self.first]
        if self._joined is None:
            self._joined = ScrollbackLine.join(self._open)
        return self._joined

    def _complete(self) -> None:
        line = self._open[0] if len(self._open) == 1 else ScrollbackLine.join(self._open)
        self._open.clear()
        self._open_width = 0
        self._lines.append(line)
        self.cells += 1
        for columns, rows in self._rows.items():
            rows.append(rows[-1] + rows_of(line.width, columns))

    def _evict(self) -> None:
        while self.cells > self.max_cells and self._lines:
            self.cells -= len(self._lines.popleft()) + 1
            self.first += 1
        while self.cells > self.max_cells and len(self._open) > 1:
            row = self._open.popleft()
            self.cells -= len(row)
            self._open_width -= row.width
            self._joined = None
        if self.first - self._base > len(self._lines):
            for rows in self._rows.values():
                del rows[: self.first - self._base]
            self._base = self.first


class MemoryView:
    """A MemoryScrollback laid out at one width. Live: it follows the store."""

    def __init__(self, store: MemoryScrollback, columns: int) -> None:
        self.store = store
        self.columns = columns
        store.row_counts(columns)

    def _complete_rows(self) -> int:
        store = self.store
        rows = store.row_counts(self.columns)
        return rows[-1] - rows[store.first - store._base]

    def __len__(self) -> int:
        return self._complete_rows() + -(-self.store._open_width // self.columns)

    def __getitem__(self, row: int) -> list[Cell]:
        if not 0 <= row < len(self):
            raise IndexError(row)
        number, within = self.line_at(row)
        line = self.store.line(number)
        start = -(-within * self.columns // line.scale)
        stop = (within + 1) * self.columns // line.scale
        cells = line.cells(start, stop)
        return cells + [(_UNSTYLED, " ")] * (stop - start - len(cells))

    def line_at(self, row: int) -> tuple[int, int]:
        store = self.store
        complete = self._complete_rows()
        if row >= complete:
            return store.first + len(store._lines), row - complete
        rows = store.row_counts(self.columns)
        floor = store.first - store._base
        index = bisect_right(rows, rows[floor] + row, lo=floor) - 1
        return store._base + index, rows[floor] + row - rows[index]

    def row_for(self, line: int) -> int:
        store = self.store
        rows = store.row_counts(self.columns)
        floor = store.first - store._base
        return rows[min(line, store.first + len(store._lines)) - store._base] - rows[floor]
