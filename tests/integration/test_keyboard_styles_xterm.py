"""Differential check against xterm's own key encoder in an isolated X server."""

import json
import os
import select
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from keyboard_styles_xterm_client import CAPABILITIES

from bittty import Board, KeyEvent, KeyModifiers
from bittty.connections import MemoryConnection
from bittty.model import XTERM


@pytest.mark.unix
@pytest.mark.integration
def test_keyboard_styles_against_xterm(tmp_path):
    if sys.platform == "win32" or not shutil.which("xterm") or not shutil.which("Xvfb"):
        pytest.skip("requires xterm and Xvfb")
    readfd, writefd = os.pipe()
    server = subprocess.Popen(
        ["Xvfb", "-displayfd", str(writefd), "-screen", "0", "640x480x24", "-nolisten", "tcp"],
        pass_fds=(writefd,),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    os.close(writefd)
    child = None
    try:
        assert select.select([readfd], [], [], 5)[0], "Xvfb did not start"
        number = os.read(readfd, 100).decode().strip()
        assert number.isdecimal(), "Xvfb failed to allocate a display"
        target = tmp_path / "keys.json"
        script = Path(__file__).with_name("keyboard_styles_xterm_client.py")
        child = subprocess.Popen(
            [
                "xterm",
                "-display",
                ":" + number,
                "-xrm",
                "*allowTcapOps: true",
                "-e",
                sys.executable,
                str(script),
                str(target),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        _, errors = child.communicate(timeout=30)
        assert child.returncode == 0, errors.decode()
        results = json.loads(target.read_text())
        assert results, "xterm recognised no tested keyboard modes"
        for mode, keys in results.items():
            board = Board(model=XTERM)
            wire = MemoryConnection()
            board.host.attach(wire)
            board.feed_host_data(f"\x1b[?{mode}h")
            assert keys, f"xterm returned no key capabilities for mode {mode}"
            for name, expected in keys.items():
                key, modifiers = CAPABILITIES[name]
                board.input_key_event(KeyEvent(key, KeyModifiers(modifiers)))
                assert wire.text == expected, (mode, name, wire.text, expected)
                wire.data.clear()
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            child.wait(timeout=5)
        server.terminate()
        server.wait(timeout=5)
        server.stderr.close()
        if child is not None:
            child.stderr.close()
        os.close(readfd)
