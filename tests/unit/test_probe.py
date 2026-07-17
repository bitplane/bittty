"""Phase 4: capability probing — parsing and env fallback (tty-free)."""

from bittty.caps import TerminalCaps
from bittty.terminals.probe import color_depth_from_env, parse_probe_replies, probe_caps


def test_color_depth_from_env():
    assert color_depth_from_env({"COLORTERM": "truecolor"}) == "truecolor"
    assert color_depth_from_env({"COLORTERM": "24bit"}) == "truecolor"
    assert color_depth_from_env({"TERM": "xterm-256color"}) == "256"
    assert color_depth_from_env({"TERM": "xterm"}) == "16"
    assert color_depth_from_env({"TERM": "dumb"}) == "unknown"
    assert color_depth_from_env({}) == "unknown"


def test_parse_probe_replies_full():
    # OSC 11 bg + CSI 6;h;w t (cell) + CSI 4;h;w t (window) + DA1 terminator
    buf = "\x1b]11;rgb:1a1a/2b2b/3c3c\x1b\\\x1b[6;32;16t\x1b[4;800;600t\x1b[?62;c"
    caps = parse_probe_replies(buf, {"COLORTERM": "truecolor"})
    assert caps.color_depth == "truecolor"
    assert caps.background == (0x1A, 0x2B, 0x3C)
    assert caps.cell_px == (16, 32)  # (width, height); reply was 6;height;width
    assert caps.window_px == (600, 800)


def test_parse_probe_replies_empty_is_env_only():
    caps = parse_probe_replies("", {"TERM": "xterm-256color"})
    assert caps == TerminalCaps(color_depth="256")  # depth from env, geometry unknown


def test_probe_non_tty_returns_env_caps():
    # fd None -> never touches stdin, never blocks; env-derived depth only
    written = []
    caps = probe_caps(None, written.append, {"COLORTERM": "truecolor"})
    assert caps.color_depth == "truecolor"
    assert caps.cell_px is None and caps.background is None
    assert written == []  # no query emitted on a non-tty
