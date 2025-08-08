#!/usr/bin/env bash
# compare-perf.sh — Compare performance across git refs, safely.

set -euo pipefail

# --- UI ---
RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'; BLUE=$'\033[0;34m'; NC=$'\033[0m'
say() { printf '%s\n' "$*"; }
info() { printf '%s%s%s\n' "$BLUE" "$*" "$NC"; }
ok()   { printf '%s%s%s\n' "$GREEN" "$*" "$NC"; }
warn() { printf '%s%s%s\n' "$YELLOW" "$*" "$NC"; }
err()  { printf '%s%s%s\n' "$RED" "$*" "$NC" >&2; }

# --- Defaults / CLI parsing ---
USE_WIP=0
USE_WORKTREE=0
MAKE_TARGET="perf"
JOBS=""
CPU_PIN=""

tag_includes=()     # -t PATTERN (regex). Repeatable.
branch_includes=()  # -b PATTERN (regex). Repeatable.
excludes=()         # -x PATTERN (regex). Repeatable.

usage() {
  cat <<EOF
Usage: $0 [options]

Options:
  -t PATTERN       Include tags matching regex (repeatable). Default: all tags.
  -b PATTERN       Include branches matching regex (repeatable). Default: all branches (excl current).
  -x PATTERN       Exclude refs matching regex (repeatable).
  --use-wip        Use performance tools from the current working tree (uncommitted OK).
  --worktree       Use 'git worktree' inside the temp clone (faster checkouts).
  --make-target T  Make target to run (default: perf).
  -j N             Set MAKEFLAGS=-jN.
  --cpu N          Pin to CPU core N with taskset (optional).

Examples:
  # Only tags v1.* and release branches, exclude rc:
  $0 -t '^v1\\.' -b '^release/' -x 'rc'

  # Use working-tree tools and 8-way make:
  $0 --use-wip -j 8
EOF
}

# Parse args
while (( $# )); do
  case "$1" in
    -t) tag_includes+=("$2"); shift 2 ;;
    -b) branch_includes+=("$2"); shift 2 ;;
    -x) excludes+=("$2"); shift 2 ;;
    --use-wip) USE_WIP=1; shift ;;
    --worktree) USE_WORKTREE=1; shift ;;
    --make-target) MAKE_TARGET="$2"; shift 2 ;;
    -j) JOBS="$2"; shift 2 ;;
    --cpu) CPU_PIN="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) err "Unknown arg: $1"; usage; exit 2 ;;
  esac
done

[[ -n "${JOBS}" ]] && export MAKEFLAGS="-j${JOBS}"

# --- Repo context ---
original_repo=$(pwd)
# Robust current-branch detection (handles detached HEAD)
original_branch=$(git branch --show-current || true)
[[ -z "$original_branch" ]] && original_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)
[[ "$original_branch" == "HEAD" || -z "$original_branch" ]] && original_branch=$(git rev-parse --short HEAD)

info "Performance Comparison Script"
say "=================================="
ok "Current ref: ${original_branch}"

# --- Helper: build regex from array ---
join_regex() {
  local IFS='|'
  printf '%s' "$*"
}

# GNU sort -V if available (macOS: gsort)
sort_cmd="sort"
command -v gsort >/dev/null 2>&1 && sort_cmd="gsort"

# --- Collect refs ---
tags=$(git tag | "$sort_cmd" -V || true)
# branches: local only (no remote branches)
branches=$(git branch --format='%(refname:short)' | grep -v -F -x "$original_branch" || true)

# Apply includes/excludes
filter_set() {
  local data="$1"; shift
  local includes=("$@")
  if (( ${#includes[@]} )); then
    local inc_re
    inc_re="$(join_regex "${includes[@]}")"
    printf '%s\n' "$data" | grep -E "$inc_re" || true
  else
    printf '%s\n' "$data"
  fi
}

exclude_set() {
  local data="$1"; shift
  local ex=("$@")
  if (( ${#ex[@]} )); then
    local ex_re
    ex_re="$(join_regex "${ex[@]}")"
    printf '%s\n' "$data" | grep -Ev "$ex_re" || true
  else
    printf '%s\n' "$data"
  fi
}

tags=$(exclude_set "$(filter_set "$tags" "${tag_includes[@]}")" "${excludes[@]}" | grep -v '^$' || true)
branches=$(exclude_set "$(filter_set "$branches" "${branch_includes[@]}")" "${excludes[@]}" | grep -v '^$' || true)

warn "Tags to test:"
if [[ -n "$tags" ]]; then echo "$tags" | while IFS= read -r line; do printf '  %s\n' "$line"; done; else say "  (none)"; fi
warn "Branches to test:"
if [[ -n "$branches" ]]; then echo "$branches" | while IFS= read -r line; do printf '  %s\n' "$line"; done; else say "  (none)"; fi

info "Starting…"

(
  tmpdir=$(mktemp -d)
  trap 'rm -rf "$tmpdir"' EXIT
  warn "Working in: $tmpdir"

  # Clone repository
  say "Cloning repository…"
  git clone --no-tags --mirror "$original_repo" "$tmpdir/mirror" >/dev/null
  git clone "$tmpdir/mirror" "$tmpdir/repo" >/dev/null
  cd "$tmpdir/repo"

  git config advice.detachedHead false

  # Restore runs.csv
  if [[ -f "$original_repo/logs/perf/runs.csv" ]]; then
    say "Copying existing runs.csv…"
    mkdir -p logs/perf
    cp "$original_repo/logs/perf/runs.csv" logs/perf/
  fi

  # Decide where to source perf tools from
  src_ref=""
  if (( ! USE_WIP )); then
    if git rev-parse --verify --quiet "refs/heads/$original_branch"; then
      src_ref="$original_branch"
    fi
  fi

  copy_perf_tools() {
    # Clean up old test files first
    rm -rf tests/performance/ 2>/dev/null || true

    if [[ -n "$src_ref" ]]; then
      # From branch in the clone
      git checkout "$src_ref" -- tests/performance/ 2>/dev/null || true
      git checkout "$src_ref" -- Makefile 2>/dev/null || true
    else
      # From original working tree - use find and cp
      mkdir -p tests/performance
      if [[ -d "$original_repo/tests/performance" ]]; then
        find "$original_repo/tests/performance" -type f | while IFS= read -r file; do
          rel="${file#"$original_repo"/tests/performance/}"
          tgt="tests/performance/$rel"
          mkdir -p "$(dirname "$tgt")"
          cp "$file" "$tgt" || true
        done
      fi
      if [[ -f "$original_repo/Makefile" ]]; then
        cp -f "$original_repo/Makefile" ./ 2>/dev/null || true
      fi
    fi
  }

  # Sanitize ref for branch names/paths
  safe_name() { printf '%s' "$1" | sed 's|[^a-zA-Z0-9._/-]|_|g'; }

  run_make() {
    local cmd=(make "$MAKE_TARGET")
    [[ -n "$CPU_PIN" ]] && cmd=(taskset -c "$CPU_PIN" "${cmd[@]}")
    "${cmd[@]}"
  }

  test_version_checkout_branch() {
    local ref="$1" kind="$2"
    local safe; safe=$(safe_name "$ref")
    local perf_branch="perf/${safe}"

    if git show-ref --verify --quiet "refs/heads/$perf_branch"; then
      say "Switching to existing branch $perf_branch"
      git checkout "$perf_branch" >/dev/null
    else
      git checkout "$ref" >/dev/null
      git checkout -b "$perf_branch" >/dev/null
    fi

    copy_perf_tools

    local sha; sha=$(git rev-parse --short HEAD)
    say ""
    info "Benchmarking $kind: $ref ($sha)…"
    if run_make; then
      ok "✓ Complete: $ref"
      # Stash any changes (including new files) then drop the stash
      git add -A 2>/dev/null || true
      git stash push -m "temp perf files" >/dev/null 2>&1 || true
      git stash drop >/dev/null 2>&1 || true
    else
      err "✗ Failed: $ref"
      # Clean up on failure too
      git add -A 2>/dev/null || true
      git stash push -m "temp perf files" >/dev/null 2>&1 || true
      git stash drop >/dev/null 2>&1 || true
    fi
    say ""
  }

  test_version_worktree() {
    local ref="$1" kind="$2"
    local sha dir
    sha=$(git rev-parse --short "$ref")
    dir="$tmpdir/repo-wt/$(safe_name "$ref")"
    mkdir -p "$(dirname "$dir")"
    git worktree add --detach "$dir" "$ref" >/dev/null
    (
      cd "$dir"
      copy_perf_tools
      info "Benchmarking $kind: $ref ($sha)…"
      if run_make; then ok "✓ Complete: $ref"; else err "✗ Failed: $ref"; fi
      say ""
    )
    git worktree remove --force "$dir" >/dev/null
  }

  test_version() {
    local ref="$1" kind="$2"
    if (( USE_WORKTREE )); then
      test_version_worktree "$ref" "$kind"
    else
      test_version_checkout_branch "$ref" "$kind"
    fi
  }

  # Process tags
  if [[ -n "$tags" ]]; then
    for tag in $tags; do
      test_version "$tag" "tag"
    done
  fi

  # Process branches (local only)
  if [[ -n "$branches" ]]; then
    for br in $branches; do
      [[ "$br" == "$original_branch" ]] && continue
      test_version "$br" "branch"
    done
  fi

  # Copy results back
  warn "Copying results back to original repository…"
  if [[ -d "logs/perf" ]]; then
    mkdir -p "$original_repo/logs/perf"
    find logs/perf -type f | while IFS= read -r file; do
      rel="${file#logs/perf/}"
      tgt="$original_repo/logs/perf/$rel"
      mkdir -p "$(dirname "$tgt")"
      cp "$file" "$tgt" || true
    done
  fi

  ok "Performance comparison complete."
)

warn "See: logs/perf/ (including logs/perf/runs.csv) for results."
