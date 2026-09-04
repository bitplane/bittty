"""Run inside an isolated headless tmux pane for test_keyboard_tmux."""

import json
import os
import select
import sys
import time
from pathlib import Path

from bittty import MemoryConnection
from bittty.terminals import StdioTerminal


def main():
    target = Path(sys.argv[1])
    terminal = StdioTerminal()
    connection = MemoryConnection()
    terminal.board.host.attach(connection)
    try:
        terminal.setup_terminal()
        terminal.probe_capabilities()
        terminal.handle_input(terminal.startup_input)
        terminal.board.parser.feed("\x1b[=31u")
        target.with_suffix(".ready").touch()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if not select.select([0], [], [], 0.1)[0]:
                continue
            data = os.read(0, 4096)
            if b"\x04" in data:
                terminal.handle_input(data.split(b"\x04", 1)[0])
                break
            terminal.handle_input(data)
        else:
            raise TimeoutError("tmux test did not deliver its end marker")
        target.write_text(json.dumps({"flags": terminal.host_keyboard_flags, "data": "".join(connection.data)}))
    finally:
        terminal.restore_terminal()


if __name__ == "__main__":
    main()
