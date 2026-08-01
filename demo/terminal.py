#!/usr/bin/env python3
"""bittty terminal emulator demo — a thin entry point over the stdio terminal.

The emulation lives in bittty.terminals.stdio.StdioTerminal, the reference
Terminal implementation, which uses the whole venue. The status bar and the row
it occupies are the demo's own chrome and live here, which is what the
reserved_rows / draw_chrome() seam on StdioTerminal is for.
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

from bittty.terminals.stdio import StdioTerminal

LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "demo" / "terminal.log"
logger = logging.getLogger(__name__)


class DemoTerminal(StdioTerminal):
    """A StdioTerminal with a status bar along the bottom of the venue."""

    reserved_rows = 1

    def draw_chrome(self) -> None:
        """Paint the status bar on the row kept back from the board."""
        status = f"bittty demo | {self.width}x{self.height} | exit normally to quit"
        print(f"\033[{self.height + 1}H\033[7m{status:<{self.width}}\033[0m", end="")


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


async def main() -> None:
    """Entry point."""
    signal.signal(signal.SIGINT, _signal_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _signal_handler)

    await DemoTerminal().run()


if __name__ == "__main__":
    setup_logging()
    try:
        asyncio.run(main())
    except Exception:
        logger.exception("Demo crashed")
        raise
