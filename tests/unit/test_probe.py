"""Phase 4: capability probing — parsing and env fallback (tty-free)."""

import pytest

import bittty.terminals.probe as probe_module
from bittty.caps import TerminalCaps
from bittty.terminals.probe import PROBE_QUERY, color_depth_from_env, parse_probe_replies, probe_caps


def test_color_depth_from_env():
    assert color_depth_from_env({"COLORTERM": "truecolor"}) == "truecolor"
    assert color_depth_from_env({"COLORTERM": "24bit"}) == "truecolor"
    assert color_depth_from_env({"TERM": "xterm-256color"}) == "256"
    assert color_depth_from_env({"TERM": "xterm"}) == "16"
    assert color_depth_from_env({"TERM": "dumb"}) == "unknown"
    assert color_depth_from_env({}) == "unknown"


def test_parse_probe_replies_full():
    # Two CPRs measure § as width 2; the other physical replies follow.
    buf = "\x1b[1;1R\x1b[1;3R\x1b]11;rgb:1a1a/2b2b/3c3c\x1b\\\x1b[6;32;16t\x1b[4;800;600t\x1b[?62;c"
    caps = parse_probe_replies(buf, {"COLORTERM": "truecolor"})
    assert caps.color_depth == "truecolor"
    assert caps.background == (0x1A, 0x2B, 0x3C)
    assert caps.cell_px == (16, 32)  # (width, height); reply was 6;height;width
    assert caps.window_px == (600, 800)
    assert caps.ambiguous_width == 2


def test_parse_probe_replies_empty_is_env_only():
    caps = parse_probe_replies("", {"TERM": "xterm-256color"})
    assert caps == TerminalCaps(color_depth="256")  # depth from env, geometry unknown


def test_probe_non_tty_returns_env_caps():
    # fd None -> never touches stdin, never blocks; env-derived depth only
    written = []
    caps = probe_caps(None, written.append, {"COLORTERM": "truecolor"})
    assert caps.color_depth == "truecolor"
    assert caps.cell_px is None and caps.background is None
    assert caps.ambiguous_width is None
    assert written == []  # no query emitted on a non-tty


def test_probe_reads_width_replies_until_da(monkeypatch):
    reply = b"\x1b[1;1R\x1b[1;3R\x1b[?62;c"
    monkeypatch.setattr(probe_module.os, "isatty", lambda fd: True)
    monkeypatch.setattr(probe_module.select, "select", lambda *args: ([7], [], []))
    monkeypatch.setattr(probe_module.os, "read", lambda fd, size: reply)
    written = []

    caps = probe_caps(7, written.append, {}, timeout=0.1)

    assert caps.ambiguous_width == 2
    assert written == [PROBE_QUERY]


def test_probe_timeout_keeps_width_unknown(monkeypatch):
    monkeypatch.setattr(probe_module.os, "isatty", lambda fd: True)
    monkeypatch.setattr(probe_module.select, "select", lambda *args: ([], [], []))
    written = []

    caps = probe_caps(7, written.append, {}, timeout=0.1)

    assert caps.ambiguous_width is None
    assert written == [PROBE_QUERY]


@pytest.mark.parametrize(
    ("positions", "expected"),
    [
        ("\x1b[4;7R\x1b[4;8R", 1),
        ("\x1b[4;7R\x1b[4;9R", 2),
        ("\x1b[4;7R\x1b[5;8R", None),
        ("\x1b[4;7R\x1b[4;10R", None),
        ("\x1b[4;7R", None),
    ],
)
def test_ambiguous_width_probe_validation(positions, expected):
    assert parse_probe_replies(positions, {}).ambiguous_width == expected


def test_probe_query_measures_and_cleans_up_ambiguous_character():
    assert PROBE_QUERY.count("\x1b[6n") == 2
    assert "§" in PROBE_QUERY
    assert "\x1b[2K" in PROBE_QUERY
    assert PROBE_QUERY.endswith("\x1b[c")


def test_terminal_caps_rejects_invalid_ambiguous_width():
    with pytest.raises(ValueError):
        TerminalCaps(ambiguous_width=3)
