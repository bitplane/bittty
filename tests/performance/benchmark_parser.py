#!/usr/bin/env python3
"""Benchmark script to compare parser performance."""

import time
import sys
from pathlib import Path

from bittty.terminal import Terminal
from bittty.parser import Parser


def benchmark_parser(ansi_content: str, runs: int = 5) -> list[float]:
    """Benchmark the parser with the given ANSI content."""
    times = []

    for i in range(runs):
        terminal = Terminal()
        parser = Parser(terminal)

        start_time = time.perf_counter()
        parser.feed(ansi_content)
        end_time = time.perf_counter()

        elapsed = end_time - start_time
        times.append(elapsed)
        print(f"Run {i+1}: {elapsed:.6f} seconds")

    return times


def main():
    # Read the static.ansi file
    ansi_file = Path("static.ansi")
    if not ansi_file.exists():
        print("Error: static.ansi file not found")
        return 1

    with open(ansi_file, "r", encoding="utf-8") as f:
        ansi_content = f.read()

    print(f"ANSI file size: {len(ansi_content)} characters")
    print("Running benchmark with 5 iterations...\n")

    times = benchmark_parser(ansi_content, runs=5)

    print("\nResults:")
    print(f"Average: {sum(times) / len(times):.6f} seconds")
    print(f"Min:     {min(times):.6f} seconds")
    print(f"Max:     {max(times):.6f} seconds")

    return 0


if __name__ == "__main__":
    sys.exit(main())
