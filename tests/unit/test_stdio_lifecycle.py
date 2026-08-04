"""StdioTerminal's lifecycle, on a real PTY: raw mode, probe, run loop, teardown.

The outer terminal is played by this test: sys.stdin becomes the slave side of a
real pseudo-terminal, the probe's DA1-terminated handshake is answered with
canned replies (so it returns immediately, no timeout), and keystrokes are typed
through the master exactly as a terminal emulator would deliver them.
"""

import asyncio
import os
import sys

import pytest

from bittty.operations import Operation
from bittty.terminals import StdioTerminal
from bittty.terminals.stdio import HostInputSink

termios = pytest.importorskip("termios", reason="the lifecycle runs on a real Unix pty")

# What a cooperative outer terminal answers to PROBE_QUERY, in reply order:
# CPR pairs measuring ambiguous width (1) and grapheme width (2), background
# colour, cell and window pixel sizes, mode 2027 reset (mutable), and the
# Primary DA reply that terminates the handshake.
_PROBE_REPLIES = (
    b"\033[1;1R\033[1;2R"
    b"\033[1;1R\033[1;3R"
    b"\033]11;rgb:1111/2222/3333\007"
    b"\033[6;20;10t"
    b"\033[4;480;800t"
    b"\033[?2027;2$y"
    b"\033[?62;1c"
)


class _PtyStdin:
    """Swap sys.stdin for the slave side of a real pseudo-terminal."""

    def __init__(self):
        self.master, self.slave = os.openpty()
        self._old_stdin = sys.stdin
        sys.stdin = os.fdopen(self.slave, "rb", buffering=0, closefd=False)

    def close(self):
        sys.stdin = self._old_stdin
        os.close(self.slave)
        os.close(self.master)


def test_run_loop_end_to_end_on_a_real_pty(capsys):
    """Setup, shell, keystrokes, render, exit, restore — the whole life.

    The probe cannot be answered here: run() calls setup and probe
    synchronously, so no task on this loop runs until they finish — the probe
    times out exactly as under a real terminal that answers nothing. The
    answered-probe path has its own test below.
    """
    stdin = _PtyStdin()
    try:
        term = StdioTerminal()
        term.board.command = "/bin/sh"  # hermetic: not the developer's login shell

        async def outer_terminal_user():
            while term.board.process is None:  # setup + probe done, shell spawned
                await asyncio.sleep(0.01)
            os.write(stdin.master, b"echo MARKER\r")
            while "MARKER" not in term.board.capture_text():  # round-tripped
                await asyncio.sleep(0.01)
            os.write(stdin.master, b"exit\r")

        async def main():
            await asyncio.gather(term.run(), outer_terminal_user())

        asyncio.run(asyncio.wait_for(main(), timeout=10))
    finally:
        stdin.close()

    # Raw mode really engaged on the tty and was really restored.
    assert term.old_termios is not None
    assert term.host_grapheme_mutable is False  # nobody answered the probe

    out = capsys.readouterr().out
    assert "\033[?1004h" in out  # setup asked the host for focus reports
    assert "MARKER" in out  # the child's output was rendered
    assert "\033[?1004l" in out and "\033[0q" in out  # teardown restored the host
    assert term.board.process is None  # cleanup reaped the child
    assert term.running is False


def test_probe_parses_a_cooperative_terminals_replies(capsys):
    """The DA1-terminated handshake, answered like a real terminal would.

    The slave is put in raw mode first (setup_terminal's job in real life), so
    the pre-buffered replies survive to be read — in canonical mode they would
    sit unread in the line buffer.
    """
    import tty

    stdin = _PtyStdin()
    try:
        tty.setraw(stdin.slave)
        os.write(stdin.master, _PROBE_REPLIES)
        term = StdioTerminal()
        term.probe_capabilities()
    finally:
        stdin.close()

    assert term.initial_ambiguous_width == 1
    assert term.host_grapheme_mutable is True
    assert term.initial_grapheme_clustering is False  # 2027;2 = reset
    assert term.board.caps.cell_px == (10, 20)
    assert "\033[c" in capsys.readouterr().out  # the DA query went out


def test_input_loop_stops_on_stdin_eof():
    """A closed stdin (read returns empty) ends the loop rather than spinning."""
    read_fd, write_fd = os.pipe()
    old_stdin = sys.stdin
    sys.stdin = os.fdopen(read_fd, "rb", buffering=0, closefd=False)
    try:
        term = StdioTerminal()
        os.close(write_fd)  # EOF pending on first read
        asyncio.run(asyncio.wait_for(term.input_loop(), timeout=5))
        assert term.running is False
    finally:
        sys.stdin = old_stdin
        os.close(read_fd)


def test_setup_without_a_tty_degrades_gracefully(capsys):
    """No tty on stdin: raw mode is skipped, the setup sequence still goes out."""
    term = StdioTerminal()
    term.setup_terminal()  # pytest's stdin has no usable fileno
    assert term.old_termios is None
    assert "\033[?1004h" in capsys.readouterr().out


def test_probe_without_a_tty_yields_env_caps_only():
    """fd-less probe: no queries written, grapheme mode unknown, not mutable."""
    term = StdioTerminal()
    term.probe_capabilities()
    assert term.host_grapheme_mutable is False
    assert term.initial_grapheme_clustering is None


def test_host_input_operation_without_raw_bytes_is_dropped():
    """The input direction routes by raw prefix; an op with no raw has no route."""
    term = StdioTerminal()
    sent = []
    term.board.input = sent.append
    HostInputSink(term).handle_operation(Operation("PRINT", ("x",), None))
    assert sent == []


def test_windows_shell_fallbacks_name_a_known_shell():
    term = StdioTerminal()
    term.is_windows = True
    assert term.get_default_shell() in ("pwsh", "powershell", "cmd")


def test_unix_shell_falls_back_when_env_shell_is_bogus(monkeypatch):
    term = StdioTerminal()
    monkeypatch.setenv("SHELL", "/nonexistent/shell")
    shell = term.get_default_shell()
    assert shell != "/nonexistent/shell"
    assert os.path.exists(shell) or shell == "sh"


def test_keyboard_indicator_leds_mirror_via_decll(capsys):
    term = StdioTerminal()
    term.on_keyboard_indicator(True, False, True)
    assert capsys.readouterr().out == "\033[0q\033[1q\033[3q"
    term.on_keyboard_indicator(False, False, False)
    assert capsys.readouterr().out == "\033[0q"


def test_repeated_mouse_capture_mode_is_not_reenabled(capsys):
    term = StdioTerminal()
    term.on_mouse_capture("basic")
    capsys.readouterr()
    term.on_mouse_capture("basic")  # same mode again: nothing to do
    assert capsys.readouterr().out == ""


def test_malformed_sgr_mouse_report_is_not_intercepted():
    term = StdioTerminal()
    assert term.handle_sgr_mouse_sequence("\033[<a;b;cM") is False


@pytest.mark.parametrize(
    ("sequence", "expected"),
    [
        ("\033[<8;2;3M", (2, 3, 0, "press", {"meta"})),
        ("\033[<32;4;5M", (4, 5, 0, "move", set())),
    ],
)
def test_sgr_mouse_meta_and_motion_decode(sequence, expected):
    term = StdioTerminal()
    seen = []
    term.board.display.input_mouse = lambda *args: seen.append(args)
    assert term.handle_sgr_mouse_sequence(sequence) is True
    assert seen == [expected]
