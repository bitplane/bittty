#!/usr/bin/env python3
"""bittty terminal emulator demo — a thin entry point over the stdio terminal.

The chrome logic lives in bittty.terminals.stdio.StdioTerminal, the reference
Terminal implementation. This file only wires up logging + signals and runs it,
so it stays a working `python3 demo/terminal.py` entry point.
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

from bittty.terminals.stdio import StdioTerminal

LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "demo" / "terminal.log"
logger = logging.getLogger(__name__)


def setup_logging() -> None:
    """Write demo and bittty logs to logs/demo/terminal.log."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=LOG_PATH,
        filemode="w",
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logger.info("Demo logging started: %s", LOG_PATH)


def _signal_handler(signum, frame) -> None:
    logger.info("Received signal %s", signum)
    sys.exit(0)


def _sigwinch_handler(signum, frame) -> None:
    display = getattr(_sigwinch_handler, "display", None)
    if display is not None:
        display.handle_resize()


async def main() -> None:
    """Entry point."""
    signal.signal(signal.SIGINT, _signal_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _signal_handler)

    display = StdioTerminal()
    if hasattr(signal, "SIGWINCH"):
        _sigwinch_handler.display = display
        signal.signal(signal.SIGWINCH, _sigwinch_handler)

    await display.run()


if __name__ == "__main__":
    setup_logging()
    try:
        asyncio.run(main())
    except Exception:
        logger.exception("Demo crashed")
        raise
