#!/usr/bin/env python3
"""Benchmark script to compare parser performance."""

import gzip
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from bittty.parser import Parser
from bittty.terminal import Terminal


def get_git_commit_hash() -> str:
    """Get the current git commit hash."""
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("ascii").strip()
    except Exception:
        return "N/A"


def benchmark_parser(ansi_content: str, runs: int = 5) -> list[float]:
    """Benchmark the parser with the given ANSI content."""
    times = []

    for _ in range(runs):
        terminal = Terminal()
        parser = Parser(terminal)

        start_time = time.perf_counter()
        parser.feed(ansi_content)
        end_time = time.perf_counter()

        elapsed = end_time - start_time
        times.append(elapsed)

    return times


def main():
    """Main function to run the benchmark."""

    times = 10

    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    # We assume this script is in tests/performance, so we go up two levels
    # to get to the project root, then down into tests to find the files.
    # This is so no matter where you run the script from, it finds the files.
    test_dir = Path(__file__).parent.parent
    gzipped_files = sorted(list(test_dir.rglob("*.ansi.gz")))

    if not gzipped_files:
        print("Error: No *.ansi.gz files found in the tests directory.", file=sys.stderr)
        return 1

    commit_hash = get_git_commit_hash()

    for ansi_file in gzipped_files:
        with gzip.open(ansi_file, "rt", encoding="utf-8") as f:
            ansi_content = f.read()

        report_lines = [
            f"Benchmark Report for: {ansi_file.name}",
            f"Git Commit Hash:      {commit_hash}",
            f"Timestamp:            {datetime.now().isoformat()}",
            f"File Size:            {len(ansi_content)} characters",
            "Runs:                  {times}",
            "",
        ]

        times = benchmark_parser(ansi_content, runs=times)

        for i, elapsed in enumerate(times):
            report_lines.append(f"Run {i+1}: {elapsed:.6f} seconds")

        report_lines.extend(
            [
                "",
                "Results:",
                f"Average: {sum(times) / len(times):.6f} seconds",
                f"Min:     {min(times):.6f} seconds",
                f"Max:     {max(times):.6f} seconds",
            ]
        )

        report = "\n".join(report_lines)
        print(report)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file_name = f"{timestamp}_{ansi_file.stem}_perf.log"
        log_file_path = logs_dir / log_file_name

        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write(report)
            f.write("\n")

        print(f"\nReport saved to {log_file_path}")
        print("-" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
