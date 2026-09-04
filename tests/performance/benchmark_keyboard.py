"""Input microbenchmarks; run directly before and after keyboard changes."""

import argparse
from statistics import median
from timeit import repeat

from bittty import MemoryConnection
from bittty.terminals import StdioTerminal


def main(*, baseline=False):
    terminal = StdioTerminal()
    connection = MemoryConnection()
    terminal.board.host.attach(connection)
    cases = {
        "typed ASCII": lambda: terminal.board.input_key("a"),
        "stdio ASCII 4K": lambda: terminal.handle_input("a" * 4096),
        "paste 64K": lambda: terminal.board.input_paste("a" * 65536),
        "stdio CSI burst": lambda: terminal.handle_input("\x1b[97;5u" * 100),
    }
    for name, operation in cases.items():

        def run(operation=operation):
            operation()
            connection.data.clear()

        samples = repeat(run, number=1000, repeat=5)
        print(f"{name}: {median(samples) * 1000:.2f} us/call")

    if baseline:
        return
    terminal.host_keyboard_flags = 31
    terminal.board.parser.feed("\x1b[=31u")

    def enhanced_burst():
        terminal.handle_input("\x1b[97;1:2;97u" * 100)
        connection.data.clear()

    samples = repeat(enhanced_burst, number=1000, repeat=5)
    print(f"stdio enhanced burst (100 events): {median(samples) * 1000:.2f} us/call")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", action="store_true", help="run only workloads supported by the old checkout")
    main(baseline=parser.parse_args().baseline)
