"""Ask a real xterm for its current key encodings via XTGETTCAP."""

import json
import os
import select
import sys
import time
from pathlib import Path

CAPABILITIES = {
    "kf1": ("f1", 0),
    "kf6": ("f6", 0),
    "kf9": ("f9", 0),
    "kf13": ("f13", 0),
    "kcuu1": ("up", 0),
    "khome": ("home", 0),
    "kend": ("end", 0),
    "kich1": ("insert", 0),
    "kpp": ("pageup", 0),
    "knp": ("pagedown", 0),
    "kUP": ("up", 1),
    "kHOM": ("home", 1),
}


def query(data, terminator):
    os.write(1, data)
    result = b""
    deadline = time.monotonic() + 2
    while not result.endswith(terminator):
        if not select.select([0], [], [], max(0, deadline - time.monotonic()))[0]:
            raise TimeoutError(f"xterm did not answer {data!r}")
        result += os.read(0, 4096)
    return result


def main(target):
    import tty

    tty.setraw(0)
    results = {}
    for mode in (1051, 1052, 1053, 1060, 1061):
        status = query(f"\x1b[?{mode}h\x1b[?{mode}$p".encode(), b"$y")
        if status != f"\x1b[?{mode};1$y".encode():
            continue  # xterm builds can omit individual keyboard families
        keys = {}
        for name in CAPABILITIES:
            reply = query(b"\x1bP+q" + name.encode().hex().encode() + b"\x1b\\", b"\x1b\\")
            if reply.startswith(b"\x1bP1+r") and b"=" in reply:
                keys[name] = bytes.fromhex(reply.split(b"=", 1)[1][:-2].decode()).decode("ascii")
        results[mode] = keys
    Path(target).write_text(json.dumps(results))


if __name__ == "__main__":
    main(sys.argv[1])
