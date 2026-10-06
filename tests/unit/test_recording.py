"""Recording the host line as asciicast v2, and replaying a recording down a cable.

The recorder is a tap on the host port, so it sees what crosses the line whatever
the cable is. The replay is a cable, so a board plays it back exactly as it would
take a child's output.
"""

import asyncio
import io
import itertools
import json
import time

import pytest

from bittty import Board, MemoryConnection
from bittty.connections import Cast, CastRecorder, CastReplay
from bittty.present import ChildExited


class Recorder:
    keeps_scrollback = False

    def __init__(self):
        self.events = []

    def present(self, event):
        self.events.append(event)


def _ticks():
    """A clock that moves on half a second each time it is read, from long before the recording."""
    return itertools.count(100, 0.5).__next__


def _tapped(**kwargs):
    board = Board(width=10, height=3)
    stream = io.StringIO()
    board.host.tap = CastRecorder(stream, board.width, board.height, clock=_ticks(), **kwargs)
    return board, stream


def _cast(stream):
    lines = stream.getvalue().splitlines()
    return json.loads(lines[0]), [json.loads(line) for line in lines[1:]]


async def _until(condition):
    for _ in range(500):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("timed out")


async def _pump(board, *chunks):
    """Plug a cable carrying `chunks` into the board and let it play out."""
    board.connect(MemoryConnection(list(chunks)))
    await _until(lambda: board.host.connection._inbound == [])
    await asyncio.sleep(0.02)


# --- recording --- #


def test_a_recording_starts_with_an_asciicast_v2_header():
    _, stream = _tapped(env={"TERM": "xterm-256color"})
    header, events = _cast(stream)
    assert (header["version"], header["width"], header["height"]) == (2, 10, 3)
    assert header["env"] == {"TERM": "xterm-256color"}
    assert events == []


@pytest.mark.asyncio
async def test_the_childs_output_is_recorded_timed_from_the_start():
    board, stream = _tapped()
    await _pump(board, b"one", b"two")
    assert _cast(stream)[1] == [[0.5, "o", "one"], [1.0, "o", "two"]]
    assert board.capture_text() == "onetwo"


@pytest.mark.asyncio
async def test_a_character_split_across_two_reads_is_recorded_whole():
    board, stream = _tapped()
    snowman = "☃".encode()
    await _pump(board, snowman[:1], snowman[1:])
    assert [event[2] for event in _cast(stream)[1]] == ["☃"]


def test_keys_sent_to_the_child_are_not_recorded_by_default():
    board, stream = _tapped()
    board.host.attach(MemoryConnection())
    board.input_text("secret")
    assert _cast(stream)[1] == []


def test_keys_sent_to_the_child_are_recorded_when_asked():
    board, stream = _tapped(record_input=True)
    board.host.attach(MemoryConnection())
    board.input_text("ls")
    board.host.write_bytes(b"\x1b[A")
    assert [event[1:] for event in _cast(stream)[1]] == [["i", "ls"], ["i", "\x1b[A"]]


def test_a_resize_is_recorded_as_columns_by_rows():
    board, stream = _tapped()
    board.host.attach(MemoryConnection())
    board.resize(20, 5)
    assert [event[1:] for event in _cast(stream)[1]] == [["r", "20x5"]]


def test_any_cable_is_told_of_a_resize_not_only_a_pty():
    board = Board(width=10, height=3)
    wire = MemoryConnection()
    board.host.attach(wire)
    board.resize(20, 5)
    assert wire.resizes == [(5, 20)]


def test_a_recording_reads_back():
    board, stream = _tapped()
    board.host.attach(MemoryConnection())
    board.resize(20, 5)
    stream.seek(0)
    cast = Cast.load(stream)
    assert (cast.width, cast.height, cast.events) == (10, 3, [(0.5, "r", "20x5")])


def test_only_asciicast_v2_is_read():
    with pytest.raises(ValueError, match="v2"):
        Cast.load(io.StringIO('{"version": 3}\n'))


# --- replay --- #


async def _replayed(cast, board=None, **kwargs):
    board = board or Board(width=4, height=2)
    recorder = Recorder()
    board.display.attach(recorder)
    board.connect(CastReplay(cast, **kwargs))
    await _until(lambda: any(isinstance(event, ChildExited) for event in recorder.events))
    return board, recorder


@pytest.mark.asyncio
async def test_a_replay_plays_the_output_on_a_board_sized_as_the_recording_began():
    cast = Cast(10, 3, [(0.0, "o", "hello\r\n"), (0.0, "i", "ignored"), (0.0, "o", "world")])
    board, _ = await _replayed(cast)
    assert (board.width, board.height) == (10, 3)
    assert board.capture_text() == "hello\nworld"


@pytest.mark.asyncio
async def test_a_resize_in_the_recording_resizes_the_board():
    board, _ = await _replayed(Cast(10, 3, [(0.0, "r", "20x5")]))
    assert (board.width, board.height) == (20, 5)


@pytest.mark.asyncio
async def test_the_end_of_a_replay_is_a_child_exit_with_no_status():
    _, recorder = await _replayed(Cast(10, 3, [(0.0, "o", "x")]))
    assert [event for event in recorder.events if isinstance(event, ChildExited)] == [ChildExited(None)]


@pytest.mark.asyncio
async def test_a_replay_keeps_the_recordings_time_divided_by_its_speed():
    started = time.monotonic()
    await _replayed(Cast(10, 3, [(0.0, "o", "a"), (2.0, "o", "b")]), speed=10)
    assert 0.2 <= time.monotonic() - started < 1.5


@pytest.mark.asyncio
async def test_an_idle_limit_caps_each_pause():
    started = time.monotonic()
    board, _ = await _replayed(Cast(10, 3, [(0.0, "o", "a"), (60.0, "o", "b")]), idle_limit=0)
    assert time.monotonic() - started < 5
    assert board.capture_text() == "ab"


@pytest.mark.asyncio
async def test_a_session_recorded_and_replayed_draws_the_same_screen():
    board, stream = _tapped()
    await _pump(board, b"\x1b[31mred\x1b[0m\r\n", "ünï\r\n".encode(), b"\x1b[2;3Hx")
    stream.seek(0)
    replayed, _ = await _replayed(Cast.load(stream), board=Board(width=4, height=2), idle_limit=0)
    assert replayed.capture_pane() == board.capture_pane()
