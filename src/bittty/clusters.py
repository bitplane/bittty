"""Grapheme-cluster assembly: writing text that is not finished arriving.

An extended grapheme cluster can straddle a chunk boundary. `👨` arrives and is
painted; the next chunk opens with ZWJ + `👩`, which means what was painted was
never a complete glyph — it has to be retracted and repainted as one wider one.

So writes here are *speculative*. Each one leaves a `_ClusterTail`: where the
glyph went, what it displaced (`restore_cells` / `insert_restore`), and enough
of the surrounding machine state to prove nothing has moved since. When the next
chunk extends the cluster, `_tail_is_valid` re-checks all of it — same page, same
row object, same cursor, same modes, same width policy, and the cell still holds
exactly what was written — before it dares undo anything. If any of that fails
the speculation is abandoned rather than corrupting the screen.

`_PendingPrefix` is the mirror case: a chunk ending in something that only joins
*forwards* (Prepend, e.g. U+0600) is parked rather than painted, because where it
lands depends on what comes next.

Clusters longer than `_MAX_CLUSTER_CODEPOINTS` are truncated for display, and the
tail keeps `_OVERFLOW_CONTEXT` code points so later marks still join the same
cluster instead of starting a new one.

The board only pays for any of this when mode 2027 is on: `Blitter` swaps its
`write_text` for this object's `write` on the instance, so the default path never
reaches here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from wcwidth import iter_graphemes

from .style import Style, parse_sgr_sequence
from .video import Cell, Video

if TYPE_CHECKING:
    from .devices.blitter import Blitter
    from .width import WidthPolicy


_MAX_CLUSTER_CODEPOINTS = 256  # display cap for one cluster
_OVERFLOW_CONTEXT = 32  # code points kept so later marks still join an overflowed cluster
_ASCII_KEYCAP_BASES = frozenset("#*0123456789")  # bases that a keycap sequence can widen


@dataclass(slots=True)
class _ClusterTail:
    page: Video
    row: list
    x: int
    y: int
    text: str
    width: int
    style: Style
    cursor_x: int
    cursor_y: int
    insert_mode: bool
    auto_wrap: bool
    width_policy: WidthPolicy
    board_width: int
    board_height: int
    write_left: int
    write_right: int
    overflow: bool = False
    context: str = ""
    restore_start: int = 0
    restore_cells: tuple[Cell, ...] = ()
    insert_restore: tuple[Cell, ...] = ()


@dataclass(slots=True)
class _PendingPrefix:
    text: str
    page: Video
    row: list
    cursor_x: int
    cursor_y: int
    insert_mode: bool
    auto_wrap: bool
    width_policy: WidthPolicy
    board_width: int
    board_height: int


class ClusterWriter:
    """Assembles grapheme clusters for a Blitter, holding its own speculation state."""

    def __init__(self, blitter: Blitter) -> None:
        self._blitter = blitter
        self._tail: _ClusterTail | None = None
        self._prefix: _PendingPrefix | None = None

    def reset(self) -> None:
        """Forget streaming state without changing already-written cells."""
        self._tail = None
        self._prefix = None

    def write(self, text: str, ansi_code: str = "") -> None:
        """Write text, assembling grapheme clusters across chunk boundaries."""
        board = self._blitter.board
        code_to_use = ansi_code if ansi_code else board.style.current
        style = code_to_use if isinstance(code_to_use, Style) else parse_sgr_sequence(code_to_use)
        self._write_clustered_text(board.charset.translate(text), style)

    def _tail_is_valid(self, tail: _ClusterTail) -> bool:
        blitter = self._blitter
        board = blitter.board
        if (
            blitter.current_page is not tail.page
            or board.width != tail.board_width
            or board.height != tail.board_height
            or board.cursor.x != tail.cursor_x
            or board.cursor.y != tail.cursor_y
            or board.modes.insert_mode != tail.insert_mode
            or board.modes.auto_wrap != tail.auto_wrap
            or board.width_policy != tail.width_policy
            or not (0 <= tail.y < tail.page.height and 0 <= tail.x < tail.page.width)
            or tail.page.grid[tail.y] is not tail.row
        ):
            return False
        head = tail.page.get_cell(tail.x, tail.y)
        if head[0] != tail.style or str(head[1]) != tail.text:
            return False
        if tail.width == 2:
            return tail.x + 1 < tail.page.width and tail.page.get_cell(tail.x + 1, tail.y) == (tail.style, "")
        return type(head[1]) is str

    def _prefix_is_valid(self, prefix: _PendingPrefix) -> bool:
        blitter = self._blitter
        board = blitter.board
        return (
            blitter.current_page is prefix.page
            and board.width == prefix.board_width
            and board.height == prefix.board_height
            and board.cursor.x == prefix.cursor_x
            and board.cursor.y == prefix.cursor_y
            and board.modes.insert_mode == prefix.insert_mode
            and board.modes.auto_wrap == prefix.auto_wrap
            and board.width_policy == prefix.width_policy
            and 0 <= prefix.cursor_y < prefix.page.height
            and prefix.page.grid[prefix.cursor_y] is prefix.row
        )

    @staticmethod
    def _is_prepend_cluster(text: str) -> bool:
        """Whether a trailing cluster joins a following ordinary base."""
        iterator = iter_graphemes(text + "A")
        return next(iterator, "") == text + "A"

    def _remember_prefix(self, text: str) -> None:
        blitter = self._blitter
        board = blitter.board
        y = board.cursor.y
        self._prefix = _PendingPrefix(
            text=text[-_MAX_CLUSTER_CODEPOINTS:],
            page=blitter.current_page,
            row=blitter.current_page.grid[y],
            cursor_x=board.cursor.x,
            cursor_y=y,
            insert_mode=board.modes.insert_mode,
            auto_wrap=board.modes.auto_wrap,
            width_policy=board.width_policy,
            board_width=board.width,
            board_height=board.height,
        )

    def _snapshot_glyph_target(self, x: int, y: int, right: int) -> tuple[int, tuple[Cell, ...], tuple[Cell, ...]]:
        blitter = self._blitter
        page = blitter.current_page
        row = page.grid[y]
        if blitter.board.modes.insert_mode:
            return x, (), tuple(row[max(x, right - 2) : right])

        start = page.owner_x(x, y)
        end = min(right, x + 2)
        if end < right and row[end][1] == "":
            end += 1
        return start, tuple(row[start:end]), ()

    def _remember_tail(
        self,
        x: int,
        y: int,
        text: str,
        width: int,
        style: Style,
        bounds: tuple[int, int],
        *,
        overflow=False,
        previous: _ClusterTail | None = None,
        restore_start=0,
        restore_cells=(),
        insert_restore=(),
    ) -> None:
        blitter = self._blitter
        board = blitter.board
        if previous is not None:
            restore_start = previous.restore_start
            restore_cells = previous.restore_cells
            insert_restore = previous.insert_restore
        tail = self._tail
        if tail is None:
            self._tail = _ClusterTail(
                page=blitter.current_page,
                row=blitter.current_page.grid[y],
                x=x,
                y=y,
                text=text,
                width=width,
                style=style,
                cursor_x=board.cursor.x,
                cursor_y=board.cursor.y,
                insert_mode=board.modes.insert_mode,
                auto_wrap=board.modes.auto_wrap,
                width_policy=board.width_policy,
                board_width=board.width,
                board_height=board.height,
                write_left=bounds[0],
                write_right=bounds[1],
                overflow=overflow,
                context=text[-_OVERFLOW_CONTEXT:],
                restore_start=restore_start,
                restore_cells=restore_cells,
                insert_restore=insert_restore,
            )
            return

        tail.page = blitter.current_page
        tail.row = blitter.current_page.grid[y]
        tail.x = x
        tail.y = y
        tail.text = text
        tail.width = width
        tail.style = style
        tail.cursor_x = board.cursor.x
        tail.cursor_y = board.cursor.y
        tail.insert_mode = board.modes.insert_mode
        tail.auto_wrap = board.modes.auto_wrap
        tail.width_policy = board.width_policy
        tail.board_width = board.width
        tail.board_height = board.height
        tail.write_left = bounds[0]
        tail.write_right = bounds[1]
        tail.overflow = overflow
        tail.context = text[-_OVERFLOW_CONTEXT:]
        tail.restore_start = restore_start
        tail.restore_cells = restore_cells
        tail.insert_restore = insert_restore

    def _write_ascii_cluster_run(self, run: str, style: Style) -> None:
        blitter = self._blitter
        board = blitter.board
        cursor = board.cursor
        if board.modes.insert_mode:
            if len(run) > 1:
                remaining = run[:-1]
                while remaining:
                    bounds = cursor.prepare_for_text_write()
                    space = bounds[1] - cursor.x
                    chunk, remaining = remaining[:space], remaining[space:]
                    blitter.current_page.insert(cursor.x, cursor.y, chunk, style, right=bounds[1])
                    cursor.advance_after_text_write(len(chunk), bounds)
            self._write_cluster_glyph(run[-1], 1, style)
            return

        remaining = run
        while remaining:
            bounds = cursor.prepare_for_text_write()
            space = bounds[1] - cursor.x
            chunk, remaining = remaining[:space], remaining[space:]
            start_x, y = cursor.x, cursor.y
            final_chunk = not remaining
            if final_chunk:
                x = start_x + len(chunk) - 1
                if run[-1] in _ASCII_KEYCAP_BASES:
                    restore_start, restore_cells, _ = self._snapshot_glyph_target(x, y, bounds[1])
                else:
                    restore_start, restore_cells = x, ()
                # If this run's prefix overwrites the head of a wide glyph whose
                # continuation is the candidate cell, record the post-prefix
                # state rather than resurrecting that old glyph on relocation.
                if restore_start < x:
                    adjusted = list(restore_cells)
                    for column in range(restore_start, x):
                        offset = column - start_x
                        if 0 <= offset < len(chunk) - 1:
                            adjusted[column - restore_start] = (style, chunk[offset])
                    adjusted[x - restore_start] = (style, " ")
                    restore_cells = tuple(adjusted)
            blitter.current_page.set(start_x, y, chunk, style)
            cursor.advance_after_text_write(len(chunk), bounds)

        self._remember_tail(
            x,
            y,
            run[-1],
            1,
            style,
            bounds,
            restore_start=restore_start,
            restore_cells=restore_cells,
        )
        blitter.last_printed_char = run[-1]

    def _write_cluster_glyph(self, text: str, width: int, style: Style) -> None:
        blitter = self._blitter
        board = blitter.board
        if width == 0 or width > board.width:
            return  # a zero-width cluster is not a glyph, and one wider than the screen cannot be shown
        cursor = board.cursor
        bounds = cursor.prepare_for_text_write()
        if width > bounds[1] - cursor.x:
            if board.modes.auto_wrap:
                cursor.x = bounds[1]
                cursor.mark_pending_wrap(bounds)
                bounds = cursor.prepare_for_text_write()
            else:
                cursor.x = bounds[1] - width
        x, y = cursor.x, cursor.y
        restore_start, restore_cells, insert_restore = self._snapshot_glyph_target(x, y, bounds[1])
        blitter.current_page.write_glyph(
            x,
            y,
            text,
            width,
            style,
            insert=board.modes.insert_mode,
            right=bounds[1],
        )
        cursor.advance_after_text_write(width, bounds)
        self._remember_tail(
            x,
            y,
            text,
            width,
            style,
            bounds,
            restore_start=restore_start,
            restore_cells=restore_cells,
            insert_restore=insert_restore,
        )
        blitter.last_printed_char = text

    def _extend_tail(self, tail: _ClusterTail, complete_text: str) -> None:
        blitter = self._blitter
        display_text = complete_text[:_MAX_CLUSTER_CODEPOINTS]
        overflow = len(complete_text) > _MAX_CLUSTER_CODEPOINTS
        if tail.overflow:
            display_text = tail.text
            overflow = True

        new_width = tail.width_policy.grapheme_width(display_text)
        if new_width == 0:
            return  # the extension left nothing displayable
        board = blitter.board
        page = tail.page

        if tail.x + new_width <= tail.write_right:
            page.resize_glyph(
                tail.x,
                tail.y,
                display_text,
                tail.width,
                new_width,
                tail.style,
                insert=tail.insert_mode,
                right=tail.write_right,
                restore_start=tail.restore_start,
                restore_cells=tail.restore_cells,
                insert_restore=tail.insert_restore,
            )
            if tail.auto_wrap:
                board.cursor.x = tail.x + new_width
                if board.cursor.x == tail.write_right:
                    board.cursor.mark_pending_wrap((tail.write_left, tail.write_right))
                else:
                    board.cursor.cancel_pending_wrap()
            else:
                board.cursor.x = min(tail.write_right - 1, tail.x + new_width)
            board.cursor.y = tail.y
            self._remember_tail(
                tail.x,
                tail.y,
                display_text,
                new_width,
                tail.style,
                (tail.write_left, tail.write_right),
                overflow=overflow,
                previous=tail,
            )
        else:
            page.remove_glyph(
                tail.x,
                tail.y,
                tail.width,
                tail.style,
                inserted=tail.insert_mode,
                right=tail.write_right,
                restore_start=tail.restore_start,
                restore_cells=tail.restore_cells,
                insert_restore=tail.insert_restore,
            )
            if tail.auto_wrap:
                board.cursor.x = tail.write_right
                board.cursor.y = tail.y
                board.cursor.mark_pending_wrap((tail.write_left, tail.write_right))
            else:
                board.cursor.x = tail.write_right - new_width
                board.cursor.y = tail.y
            self._write_cluster_glyph(display_text, new_width, tail.style)
            if self._tail is not None:
                self._tail.overflow = overflow
                self._tail.context = complete_text[-_OVERFLOW_CONTEXT:]
        if self._tail is not None:
            self._tail.context = complete_text[-_OVERFLOW_CONTEXT:]
        blitter.last_printed_char = display_text

    def _attach_to_tail(self, text: str) -> str:
        tail = self._tail
        if tail is None or not self._tail_is_valid(tail):
            self._tail = None
            return text

        base = tail.context if tail.overflow else tail.text
        iterator = iter_graphemes(base + text)
        first = next(iterator, "")
        if not first.startswith(base) or len(first) == len(base):
            return text

        consumed = len(first) - len(base)
        if tail.overflow:
            complete = tail.text
        else:
            complete = first
        self._extend_tail(tail, complete)
        if self._tail is not None and tail.overflow:
            self._tail.context = first[-_OVERFLOW_CONTEXT:]
        return text[consumed:]

    def _write_new_clusters(self, text: str, style: Style) -> None:
        blitter = self._blitter
        iterator = iter_graphemes(text)
        pending = next(iterator, None)

        ascii_parts: list[str] = []

        def flush_ascii() -> None:
            if ascii_parts:
                self._write_ascii_cluster_run("".join(ascii_parts), style)
                ascii_parts.clear()

        for cluster in iterator:
            if pending.isascii() and len(pending) == 1:
                ascii_parts.append(pending)
            else:
                flush_ascii()
                width = blitter.board.width_policy.grapheme_width(pending)
                if width:
                    display = pending[:_MAX_CLUSTER_CODEPOINTS]
                    self._write_cluster_glyph(display, blitter.board.width_policy.grapheme_width(display), style)
                    if self._tail is not None and len(pending) > _MAX_CLUSTER_CODEPOINTS:
                        self._tail.overflow = True
                        self._tail.context = pending[-_OVERFLOW_CONTEXT:]
            pending = cluster

        if self._is_prepend_cluster(pending):
            flush_ascii()
            self._remember_prefix(pending)
        elif pending.isascii() and len(pending) == 1:
            ascii_parts.append(pending)
            flush_ascii()
        else:
            flush_ascii()
            width = blitter.board.width_policy.grapheme_width(pending)
            if width:
                display = pending[:_MAX_CLUSTER_CODEPOINTS]
                self._write_cluster_glyph(display, blitter.board.width_policy.grapheme_width(display), style)
                if self._tail is not None and len(pending) > _MAX_CLUSTER_CODEPOINTS:
                    self._tail.overflow = True
                    self._tail.context = pending[-_OVERFLOW_CONTEXT:]

    def _write_clustered_text(self, text: str, style: Style) -> None:
        if not text:
            return

        prefix = self._prefix
        if prefix is None and text.isascii():
            # ASCII always starts a new cluster (the only forward-joining case,
            # Prepend, is held separately), so avoid invoking the segmenter.
            self._write_ascii_cluster_run(text, style)
            return

        if prefix is not None:
            self._prefix = None
            if self._prefix_is_valid(prefix):
                text = prefix.text + text
            else:
                prefix = None

        if prefix is None:
            text = self._attach_to_tail(text)
            if not text:
                return

        if text.isascii():
            self._write_ascii_cluster_run(text, style)
        else:
            self._write_new_clusters(text, style)
