"""Recording the host line, and playing a recording back down one, as asciicast v2.

A recording is what crossed the cable, timed: the child's output, optionally the
keys sent to it, and each resize. That is lossless and belongs to the line, so
recording is a tap on the host port (any cable) and replay is a cable of its own.
Turning a recording into frames (sampling the screen on a clock, quantising) is
lossy and belongs to whatever looks at the screen: a terminal (chrome).

asciicast v2 (https://docs.asciinema.org/manual/asciicast/v2/) holds text, so
bytes that are not UTF-8 are recorded as U+FFFD.
"""

from __future__ import annotations

import asyncio
import codecs
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from .serial_line import SerialLine


@dataclass
class Cast:
    """A recording: the screen size it began at, and its events as (seconds, code, data)."""

    width: int
    height: int
    events: list[tuple[float, str, str]] = field(default_factory=list)

    @classmethod
    def load(cls, stream: TextIO) -> Cast:
        """Read an asciicast v2 recording."""
        header = json.loads(stream.readline())
        if header.get("version") != 2:
            raise ValueError(f"not an asciicast v2 recording: version {header.get('version')!r}")
        events = [tuple(json.loads(line)) for line in stream if line.strip()]
        return cls(header["width"], header["height"], events)


def _decoder() -> codecs.IncrementalDecoder:
    return codecs.getincrementaldecoder("utf-8")("replace")


class CastRecorder:
    """A LineTap that writes what crosses the line to a stream as asciicast v2, as it happens.

    Keys sent to the child are left out unless `record_input` is set: they include
    passwords typed at prompts that never echo them. `clock` gives the time in
    seconds; the recording starts at zero when the recorder is made.
    """

    def __init__(
        self,
        stream: TextIO,
        width: int,
        height: int,
        *,
        record_input: bool = False,
        env: dict[str, str] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.stream = stream
        self.record_input = record_input
        self.clock = clock
        self.start = clock()
        self._output = _decoder()  # a character may straddle two reads
        self._input = _decoder()
        header = {"version": 2, "width": width, "height": height, "timestamp": int(time.time())}
        stream.write(json.dumps(header | ({"env": env} if env else {})) + "\n")
        stream.flush()

    def received(self, data: bytes) -> None:
        self._event("o", self._output.decode(data))

    def sent(self, data: str | bytes) -> None:
        if self.record_input:
            self._event("i", data if isinstance(data, str) else self._input.decode(data))

    def resized(self, rows: int, cols: int) -> None:
        self._event("r", f"{cols}x{rows}")

    def _event(self, code: str, data: str) -> None:
        if data:
            self.stream.write(json.dumps([round(self.clock() - self.start, 6), code, data]) + "\n")
            self.stream.flush()


class CastReplay:
    """A Connection whose far end is a recording: it plays the output back, in time.

    `speed` divides every pause; `idle_limit` caps each one first, as asciinema's
    idle_time_limit does (0 plays it all at once). A resize in the recording, and
    its starting size, reach the board the only way a far end can ask for one: as
    XTWINOPS 8. What the board transmits goes nowhere. The cable closes after the
    last event, which the board presents as the child exiting.
    """

    def __init__(self, cast: Cast, *, speed: float = 1.0, idle_limit: float | None = None) -> None:
        self.closed = False
        self._schedule: list[tuple[float, bytes]] = [(0.0, _resize_request(cast.width, cast.height))]
        due = last = 0.0
        for at, code, data in cast.events:
            if code in ("o", "r"):
                pause = at - last if idle_limit is None else min(at - last, idle_limit)
                due, last = due + max(0.0, pause) / speed, at
                payload = data.encode() if code == "o" else _resize_request(*map(int, data.split("x")))
                self._schedule.append((due, payload))
        self._next = 0
        self._started: float | None = None

    async def read_bytes_async(self, size: int = 65536) -> bytes:
        if self._next == len(self._schedule):
            self.closed = True
            return b""
        loop = asyncio.get_running_loop()
        if self._started is None:
            self._started = loop.time()
        due, data = self._schedule[self._next]
        await asyncio.sleep(max(0.0, self._started + due - loop.time()))
        self._next += 1
        return data

    def write(self, data: str) -> int:
        return len(data)

    def write_bytes(self, data: bytes) -> int:
        return len(data)

    def flush(self) -> None:
        """Nothing is buffered: what is sent goes nowhere."""

    def configure_line(self, line: SerialLine) -> None:
        """A recording has no modem to configure."""

    def resize(self, rows: int, cols: int) -> None:
        """A recording cannot be told anything."""

    def close(self) -> None:
        self.closed = True


def _resize_request(cols: int, rows: int) -> bytes:
    return f"\x1b[8;{rows};{cols}t".encode()
