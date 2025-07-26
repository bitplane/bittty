#!/usr/bin/env bash

source .venv/bin/activate

# Run pytest with coverage reports and tee output
pytest --cov="src/$1" --cov-report=html --cov-report=term-missing . 2>&1 | tee htmlcov/coverage_report.txt

# Extract just the missing coverage summary
grep -A 20 "Missing" htmlcov/coverage_report.txt > htmlcov/missing_coverage.txt
