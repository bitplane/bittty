#!/usr/bin/env python3
"""Benchmark script to compare parser performance."""

import argparse
import cProfile
import csv
import gzip
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

try:
    import plotext as plt

    HAS_PLOTEXT = True
except ImportError:
    HAS_PLOTEXT = False

from bittty.parser import Parser
from bittty.terminal import Terminal


def get_git_commit_hash() -> str:
    """Get the current git commit hash."""
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("ascii").strip()
    except Exception:
        return "N/A"


def get_git_commit_date() -> str:
    """Get commit date in ISO8601 format."""
    # Use environment variable if provided (for compare script)
    if "COMMIT_DATE" in os.environ:
        return os.environ["COMMIT_DATE"]

    try:
        return subprocess.check_output(["git", "show", "-s", "--format=%cI", "HEAD"]).decode("ascii").strip()
    except Exception:
        return datetime.now().isoformat()


def get_git_branch_name() -> str:
    """Get the current git branch name."""
    try:
        return subprocess.check_output(["git", "branch", "--show-current"]).decode("ascii").strip()
    except Exception:
        return "unknown"


def benchmark_parser(ansi_content: str, runs: int = 5, temp_profile_path: str = None) -> tuple[list[float], str]:
    """Benchmark the parser with the given ANSI content.

    Returns:
        tuple: (times_list, profile_filename)
    """
    times = []

    # Profile the first run for detailed analysis
    if temp_profile_path is None:
        branch_name = get_git_branch_name()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Use temp location, will be moved later - sanitize branch name for filesystem
        branch_safe = branch_name.replace("/", "_")
        temp_dir = tempfile.gettempdir()
        profile_filename = str(Path(temp_dir) / f"{timestamp}_{branch_safe}_profile.prof")
    else:
        profile_filename = temp_profile_path

    # Run with profiling for profile data (don't include timing)
    terminal = Terminal()
    parser = Parser(terminal)

    profiler = cProfile.Profile()
    profiler.enable()
    parser.feed(ansi_content)
    profiler.disable()

    # Save profile data
    profiler.dump_stats(profile_filename)

    # Now run without profiling for clean timing data
    for _ in range(runs):
        terminal = Terminal()
        parser = Parser(terminal)

        start_time = time.perf_counter()
        parser.feed(ansi_content)
        end_time = time.perf_counter()

        elapsed = end_time - start_time
        times.append(elapsed)

    return times, profile_filename


def update_runs_csv(csv_path: Path, run_data: dict):
    """Update runs.csv with new benchmark data, using atomic write."""
    fieldnames = [
        "run_ts",
        "commit_date",
        "branch",
        "test_case",
        "time_min",
        "runs",
        "time_mean",
        "time_median",
        "time_max",
        "dir_path",
    ]

    # Read existing data
    existing_rows = []
    if csv_path.exists():
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            existing_rows = list(reader)

    # Add new row
    existing_rows.append(run_data)

    # Write atomically via temp file
    temp_path = csv_path.with_suffix(".csv.tmp")
    with open(temp_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing_rows)

    # Atomic rename
    temp_path.rename(csv_path)


def generate_visualizations(perf_base_dir: Path):
    """Generate performance graphs for each test case."""
    if not HAS_PLOTEXT:
        print("plotext not installed, skipping visualization")
        return

    csv_path = perf_base_dir / "runs.csv"
    if not csv_path.exists():
        return

    # Read all data
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        all_data = list(reader)

    if not all_data:
        return

    # Group by test case
    test_cases = {}
    for row in all_data:
        test = row["test_case"]
        if test not in test_cases:
            test_cases[test] = []
        test_cases[test].append(row)

    # Generate a graph for each test case
    for test_name, test_data in test_cases.items():
        # Sort by commit date (oldest first for left-to-right chronological order)
        test_data.sort(key=lambda x: x["commit_date"])

        # Prepare data
        branches = []
        times = []
        for row in test_data:
            time_val = float(row["time_mean"])
            # Skip zero or negative values
            if time_val <= 0:
                continue

            # Get branch name - split on / and take last part, then truncate to 10 chars from back
            branch = row["branch"].split("/")[-1]
            if len(branch) > 10:
                branch = branch[-10:]
            branches.append(branch)
            times.append(time_val)

        # Skip if no valid data points
        if not branches or not times:
            continue

        # Create plot
        plt.clear_data()
        plt.clear_color()

        # Set theme for black background with colors
        plt.theme("dark")

        # Bar chart with branches on x-axis, time on y-axis
        plt.bar(branches, times, color="cyan")

        # Configure plot
        plt.title(f"Performance: {test_name}")
        plt.xlabel("Branch/Version")
        plt.ylabel("Time (seconds)")

        # Use linear scale for now (log scale causing issues)
        # plt.yscale("log")

        # Set size - 24 rows height, auto width based on samples
        width = max(60, len(branches) * 6 + 20)  # 6 chars per sample + margins
        plt.plotsize(width, 24)

        # Fancy border
        plt.grid(True, True)

        # Generate the plot as text
        plot_text = plt.build()

        # Save to file
        output_file = perf_base_dir / f"{test_name}.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(plot_text)

        print(f"  Generated: {output_file.relative_to(perf_base_dir.parent.parent)}")

    # Generate combined stacked chart
    generate_combined_chart(test_cases, perf_base_dir)


def generate_combined_chart(test_cases: dict, perf_base_dir: Path):
    """Generate a combined chart with all test cases."""
    if not HAS_PLOTEXT or not test_cases:
        return

    # Get all unique branches across all test cases, sorted by commit date
    all_branches = {}  # branch -> commit_date
    for test_data in test_cases.values():
        for row in test_data:
            branch = row["branch"]
            all_branches[branch] = row["commit_date"]

    # Sort branches chronologically
    sorted_branches = sorted(all_branches.keys(), key=lambda b: all_branches[b])

    # Prepare branch labels (last 10 chars)
    branch_labels = []
    for branch in sorted_branches:
        label = branch.split("/")[-1]
        if len(label) > 10:
            label = label[-10:]
        branch_labels.append(label)

    plt.clear_data()
    plt.clear_color()
    plt.theme("dark")

    # Prepare data for stacked bar chart
    all_times = []
    test_names = []
    # Sort test cases to ensure consistent order
    for test_name, test_data in sorted(test_cases.items()):
        test_names.append(test_name)
        test_times = {row["branch"]: float(row["time_mean"]) for row in test_data if float(row["time_mean"]) > 0}
        times_for_test = [test_times.get(branch, 0) for branch in sorted_branches]
        all_times.append(times_for_test)

    # Create stacked bar chart
    if all_times:
        plt.stacked_bar(branch_labels, all_times, labels=test_names)

    # Configure plot
    plt.title("Performance Comparison: All Tests")
    plt.xlabel("Branch/Version")
    plt.ylabel("Time (seconds)")

    # Set size - taller for combined chart
    width = max(80, len(branch_labels) * 8 + 30)
    plt.plotsize(width, 30)

    # Add grid and legend
    plt.grid(True, True)

    # Generate and save
    plot_text = plt.build()
    output_file = perf_base_dir / "combined.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(plot_text)

    print(f"  Generated: {output_file.relative_to(perf_base_dir.parent.parent)}")


def main():
    """Main function to run the benchmark."""

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Benchmark bittty parser performance")
    parser.add_argument("--run-name", help="Run name for this benchmark")
    parser.add_argument("--timestamp", help="Timestamp for this benchmark (default: current time)")
    parser.add_argument("--run-count", type=int, default=5, help="Number of benchmark runs (default: 5)")
    args = parser.parse_args()

    num_runs = args.run_count

    # Use project root logs/perf/parser directory structure
    project_root = Path(__file__).parent.parent.parent
    perf_base_dir = project_root / "logs" / "perf" / "parser"
    perf_base_dir.mkdir(parents=True, exist_ok=True)

    # Test cases relative to this script in tests/ subdirectory
    script_dir = Path(__file__).parent
    test_files_dir = script_dir / "tests"
    gzipped_files = sorted(list(test_files_dir.glob("*.gz")))

    if not gzipped_files:
        print("Error: No *.ansi.gz files found in the tests directory.", file=sys.stderr)
        return 1

    # Get run name and timestamp
    run_name = args.run_name or "benchmark"
    timestamp = args.timestamp or datetime.now().isoformat()

    for ansi_file in gzipped_files:
        # Extract test case name (remove .gz only)
        test_case = ansi_file.stem

        # Create timestamp for this run (include microseconds to avoid collisions)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        # Create directory structure: logs/perf/{branch}/{timestamp}/
        run_dir = perf_base_dir / run_name / timestamp
        run_dir.mkdir(parents=True, exist_ok=True)

        with gzip.open(ansi_file, "rt", encoding="utf-8") as f:
            ansi_content = f.read()

        report_lines = [
            f"Benchmark Report for: {ansi_file.name}",
            f"Test Case:            {test_case}",
            f"Run Name:             {run_name}",
            f"Timestamp:            {timestamp}",
            f"Timestamp:            {datetime.now().isoformat()}",
            f"File Size:            {len(ansi_content)} characters",
            f"Runs:                  {num_runs}",
            "",
        ]

        times, profile_filename = benchmark_parser(ansi_content, runs=num_runs)

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

        # Create descriptive filenames with run name and test case
        branch_safe = run_name.replace("/", "_")
        test_safe = test_case

        # Save to organized directory structure
        log_file_path = run_dir / f"{branch_safe}_{test_safe}.log"
        profile_path = run_dir / f"{branch_safe}_{test_safe}.prof"
        profile_txt_path = run_dir / f"{branch_safe}_{test_safe}.txt"

        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write(report)
            f.write("\n")

        # Move profile file to organized location
        if Path(profile_filename).exists():
            shutil.move(profile_filename, profile_path)

        try:
            # Use subprocess to generate profile text
            cmd = [
                sys.executable,
                "-c",
                f"""
import pstats
stats = pstats.Stats('{profile_path}')
print('Profile Report for: {ansi_file.name}')
print('Test Case: {test_case}')
print(f'Run Name: {run_name}')
print(f'Timestamp: {timestamp}')
print('=' * 80)
print()
print('TOP 30 FUNCTIONS BY CUMULATIVE TIME:')
print('-' * 50)
stats.sort_stats('cumulative').print_stats(30)
print()
print('TOP 20 FUNCTIONS BY INTERNAL TIME:')
print('-' * 50)
stats.sort_stats('tottime').print_stats(20)
""",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            with open(profile_txt_path, "w", encoding="utf-8") as f:
                f.write(result.stdout)
                if result.stderr:
                    f.write(f"\n\nErrors:\n{result.stderr}")
        except Exception as e:
            # Fallback: just create basic profile info
            with open(profile_txt_path, "w", encoding="utf-8") as f:
                f.write(f"Profile Report for: {ansi_file.name}\n")
                f.write(f"Test Case: {test_case}\n")
                f.write(f"Run Name: {run_name}\n")
                f.write(f"Timestamp: {timestamp}\n")
                f.write("=" * 80 + "\n\n")
                f.write(f"Profile data saved to: {profile_path}\n")
                f.write(f"Error generating text report: {e}\n")
                f.write("Use: python -c \"import pstats; pstats.Stats('profile.prof').print_stats()\"\n")

        # Update CSV database
        csv_path = perf_base_dir / "runs.csv"
        run_data = {
            "run_ts": datetime.now().isoformat(),
            "commit_date": timestamp,
            "branch": run_name,
            "test_case": test_case,
            "time_min": min(times),
            "runs": num_runs,
            "time_mean": statistics.mean(times),
            "time_median": statistics.median(times),
            "time_max": max(times),
            "dir_path": str(run_dir.relative_to(perf_base_dir)),
        }
        update_runs_csv(csv_path, run_data)

        # Show relative paths from project root
        rel_log = log_file_path.relative_to(project_root)
        rel_profile = profile_path.relative_to(project_root)
        rel_txt = profile_txt_path.relative_to(project_root)

        print("\nResults:")
        print(f"  Report: {rel_log}")
        print(f"  Profile: {rel_profile}")
        print(f"  Profile text: {rel_txt}")
        print(f"\nView: snakeviz {rel_profile}")
        print("-" * 80)

    # Generate visualizations
    print("Generating performance visualizations...")
    generate_visualizations(perf_base_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
