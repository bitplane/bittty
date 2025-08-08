#!/bin/bash

# Compare performance across git versions in isolated environment

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Performance Comparison Script${NC}"
echo "=================================="

# Get current repo info
original_repo=$(pwd)
original_branch=$(git branch --show-current)

# Get all tags and branches to test
echo -e "${YELLOW}Available versions:${NC}"
tags=$(git tag | sort -V)
# Get local branches excluding current, plus remote branches that aren't just origin
local_branches=$(git branch --format='%(refname:short)' | grep -v "^$original_branch$" || true)
remote_branches=$(git branch -r --format='%(refname:short)' | grep -v HEAD | grep -v '^origin$' | sed 's|origin/||' | grep -v "^$original_branch$" || true)
# Combine and deduplicate branches
branches=$(printf "%s\n%s" "$local_branches" "$remote_branches" | sort -u | grep -v '^$' || true)

echo "Tags:"
while IFS= read -r line; do echo "  $line"; done <<< "$tags"
echo "Branches:"
if [[ -n "$branches" ]]; then
    while IFS= read -r line; do echo "  $line"; done <<< "$branches"
else
    echo "  (none)"
fi
echo -e "${GREEN}Current branch: $original_branch${NC}"

echo ""
echo -e "${YELLOW}This script will:${NC}"
echo "1. Clone repo to temporary directory"
echo "2. Copy existing runs.csv to preserve data"
echo "3. Test each tag and branch with performance benchmarks"
echo "4. Copy results back to original repository"
echo "5. Clean up temporary directory"
echo ""

read -p "Continue? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

echo -e "${BLUE}Starting performance comparison...${NC}"

# Create temp directory and start subshell
(
    # Create temp directory and set cleanup trap
    tmpdir=$(mktemp -d)
    trap 'rm -rf "$tmpdir"' EXIT

    echo -e "${YELLOW}Working in temporary directory: $tmpdir${NC}"

    # Clone repository
    echo "Cloning repository..."
    git clone "$original_repo" "$tmpdir/repo"
    cd "$tmpdir/repo"

    # Silence detached HEAD warnings
    git config advice.detachedHead false

    # Copy existing runs.csv if it exists
    if [[ -f "$original_repo/logs/perf/runs.csv" ]]; then
        echo "Copying existing runs.csv..."
        mkdir -p logs/perf
        cp "$original_repo/logs/perf/runs.csv" logs/perf/
    fi

    # Test function for a given ref
    test_version() {
        local ref="$1"
        local ref_type="$2"  # "tag" or "branch"

        echo -e "${BLUE}Processing $ref_type: $ref${NC}"

        # Create/checkout performance branch
        if [[ "$ref_type" == "tag" ]]; then
            perf_branch="perf/v$ref"
        else
            perf_branch="perf/$ref"
        fi

        if git show-ref --verify --quiet "refs/heads/$perf_branch"; then
            echo "Branch $perf_branch already exists, checking out..."
            git checkout "$perf_branch"
        else
            echo "Creating new branch $perf_branch from $ref..."
            git checkout "$ref"
            git checkout -b "$perf_branch"
        fi

        # Copy current performance tools from original branch
        echo "Updating performance tools..."
        rm -rf tests/performance/ 2>/dev/null || true
        git checkout "$original_branch" -- tests/performance/ 2>/dev/null || true
        git checkout "$original_branch" -- Makefile 2>/dev/null || true

        # Commit the updated tools so they don't interfere with next checkout
        git add tests/performance/ Makefile 2>/dev/null || true
        git commit -m "Update performance tools and test data" --no-verify 2>/dev/null || true

        # Run benchmark
        echo "Running performance benchmark..."
        if make perf; then
            echo -e "${GREEN}✓ Benchmark completed for $ref${NC}"
        else
            echo -e "${RED}✗ Benchmark failed for $ref${NC}"
        fi

        echo ""
    }

    # Process all tags
    if [[ -n "$tags" ]]; then
        for tag in $tags; do
            test_version "$tag" "tag"
        done
    fi

    # Process all branches (except current)
    if [[ -n "$branches" ]]; then
        for branch in $branches; do
            # Skip if it's the original branch
            if [[ "$branch" != "$original_branch" ]]; then
                # Try local branch first, then remote
                if git show-ref --verify --quiet "refs/heads/$branch"; then
                    test_version "$branch" "branch"
                elif git show-ref --verify --quiet "refs/remotes/origin/$branch"; then
                    test_version "origin/$branch" "branch"
                else
                    echo -e "${RED}Branch $branch not found, skipping...${NC}"
                fi
            fi
        done
    fi

    # Copy results back to original repository
    echo -e "${YELLOW}Copying results back to original repository...${NC}"
    if [[ -d "logs/perf" ]]; then
        mkdir -p "$original_repo/logs/perf"

        # Copy all files and directories, creating parent dirs as needed
        find logs/perf -type f | while IFS= read -r file; do
            # Get relative path from logs/perf
            rel_path="${file#logs/perf/}"
            target_file="$original_repo/logs/perf/$rel_path"
            target_dir=$(dirname "$target_file")

            # Create target directory if it doesn't exist
            mkdir -p "$target_dir"

            # Copy the file
            cp "$file" "$target_file" || true
        done
    fi

    echo -e "${GREEN}Performance comparison complete!${NC}"
)

echo -e "${YELLOW}Check logs/perf/ for detailed results${NC}"
echo -e "${YELLOW}CSV database: logs/perf/runs.csv${NC}"