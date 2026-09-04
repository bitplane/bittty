"""Keyboard negotiation and real key delivery through a headless tmux server."""

import json
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest


@pytest.mark.unix
@pytest.mark.integration
def test_keyboard_through_headless_tmux(tmp_path):
    if shutil.which("tmux") is None:
        pytest.skip("tmux is not installed")
    socket = f"bittty-keyboard-{uuid.uuid4().hex}"
    prefix = ["tmux", "-L", socket, "-f", "/dev/null"]
    target = tmp_path / "result.json"
    script = Path(__file__).with_name("keyboard_tmux_client.py")

    def tmux(*args):
        result = subprocess.run([*prefix, *args], check=False, capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stderr
        return result

    def wait_file(path):
        deadline = time.monotonic() + 12
        while not path.exists():
            if time.monotonic() > deadline:
                pytest.fail(f"tmux keyboard client did not produce {path.name}")
            time.sleep(0.02)

    try:
        tmux(
            "new-session",
            "-d",
            "-s",
            "keyboard",
            "-x",
            "80",
            "-y",
            "24",
            shlex.join([sys.executable, str(script), str(target)]),
        )
        wait_file(target.with_suffix(".ready"))
        tmux("send-keys", "-t", "keyboard", "a", "Up", "F3", "C-a")
        tmux("send-keys", "-t", "keyboard", "-H", "04")
        wait_file(target)
        result = json.loads(target.read_text())
        if result["flags"] is None:
            assert result["data"] == "\x1b[0;;97u\x1b[A\x1b[13~\x01"
        else:
            assert result["flags"] == 31
            assert result["data"] == "\x1b[97;;97u\x1b[A\x1b[13~\x1b[97;5u"
    finally:
        subprocess.run([*prefix, "kill-server"], check=False, capture_output=True, timeout=5)
