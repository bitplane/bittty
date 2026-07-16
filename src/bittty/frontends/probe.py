"""Capability probing for the passthrough client.

Ask the real outer terminal what it can do, then hand a DisplayCaps up to the
backend. Uses a DA1-terminated handshake: fire all the queries plus a Primary DA
request, then read until the (universally answered) DA reply arrives, so optional
queries that go unanswered never make us hang. Non-tty or timeout ⇒ env/config
caps only.

Nothing here reads capabilities the backend then trusts blindly — DisplayCaps is
purely physical facts (colour depth, pixel geometry, background). Graphics-mode
reconciliation is deferred with the graphics families.
"""

from __future__ import annotations

import os
import re
import select
import time

from ..caps import DisplayCaps

# Response patterns:
#   OSC 11 ; rgb:RRRR/GGGG/BBBB   (background colour)
#   CSI 6 ; height ; width t      (cell size in pixels, reply to CSI 16 t)
#   CSI 4 ; height ; width t      (window size in pixels, reply to CSI 14 t)
#   CSI ? ... c                   (Primary DA — the handshake terminator)
_BG = re.compile(r"\]11;rgb:([0-9a-fA-F]+)/([0-9a-fA-F]+)/([0-9a-fA-F]+)")
_CELL = re.compile(r"\[6;(\d+);(\d+)t")
_WINDOW = re.compile(r"\[4;(\d+);(\d+)t")
_DA1 = re.compile(r"\[\?[0-9;]*c")

# The queries we send, ending in a Primary DA request as the terminator.
PROBE_QUERY = "\033]11;?\007\033[16t\033[14t\033[c"


def color_depth_from_env(env) -> str:
    """Best-effort colour depth from COLORTERM / TERM (no query exists for this)."""
    if env.get("COLORTERM", "") in ("truecolor", "24bit"):
        return "truecolor"
    term = env.get("TERM", "")
    if "256color" in term:
        return "256"
    if term in ("", "dumb"):
        return "unknown"
    return "16"


def _high_byte(hex_channel: str) -> int:
    """The 8-bit value of a terminal colour channel reported as 1-4 hex digits."""
    return int(hex_channel[:2].ljust(2, "0"), 16)


def parse_probe_replies(buf: str, env) -> DisplayCaps:
    """Build DisplayCaps from a probe-reply buffer, unioned with env (probe wins)."""
    background = None
    if (m := _BG.search(buf)) is not None:
        background = (_high_byte(m.group(1)), _high_byte(m.group(2)), _high_byte(m.group(3)))
    cell_px = None
    if (m := _CELL.search(buf)) is not None:  # reply is height;width
        cell_px = (int(m.group(2)), int(m.group(1)))
    window_px = None
    if (m := _WINDOW.search(buf)) is not None:
        window_px = (int(m.group(2)), int(m.group(1)))
    return DisplayCaps(
        color_depth=color_depth_from_env(env),
        cell_px=cell_px,
        window_px=window_px,
        background=background,
    )


def probe_display_caps(stdin_fd, write, env=None, timeout: float = 0.2) -> DisplayCaps:
    """Query the real terminal and return DisplayCaps; env-only on a non-tty/timeout.

    `write` is a callable that writes a str to the outer terminal (and flushes).
    """
    env = os.environ if env is None else env
    if stdin_fd is None or not os.isatty(stdin_fd):
        return parse_probe_replies("", env)

    write(PROBE_QUERY)
    buf = ""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        readable, _, _ = select.select([stdin_fd], [], [], max(0.0, end - time.monotonic()))
        if not readable:
            break
        chunk = os.read(stdin_fd, 4096)
        if not chunk:
            break
        buf += chunk.decode("utf-8", errors="replace")
        if _DA1.search(buf):  # the DA reply terminates the handshake
            break
    return parse_probe_replies(buf, env)
