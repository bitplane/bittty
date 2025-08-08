#!/usr/bin/env bash

source .venv/bin/activate

branch=$(git branch --show-current)
commit_date=$(git show -s --format=%cI HEAD)
python tests/performance/benchmark_parser.py --run-name "${1:-$branch}" --timestamp "${2:-$commit_date}"