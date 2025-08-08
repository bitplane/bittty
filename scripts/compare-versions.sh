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
MAKE_TARGET="perf"
JOBS=""
CPU_PIN=""

tag_includes=()     # -t PATTERN (regex). Repeatable.
excludes=()         # -x PATTERN (regex). Repeatable.

usage() {
  cat <<EOF
Usage: $0 [options]

Options:
  -t PATTERN       Include tags matching regex (repeatable). Default: all tags.
  -x PATTERN       Exclude refs matching regex (repeatable).
  --make-target T  Make target to run (default: perf).
  -j N             Set MAKEFLAGS=-jN.
  --cpu N          Pin to CPU core N with taskset (optional).

Examples:
  # Only tags v1.*, exclude rc:
  $0 -t '^v1\\.' -x 'rc'

  # Use 8-way make:
  $0 -j 8
EOF
}

# Parse args
while (( $# )); do
  case "$1" in
    -t) tag_includes+=("$2"); shift 2 ;;
    -x) excludes+=("$2"); shift 2 ;;
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

warn "Tags to test:"
if [[ -n "$tags" ]]; then echo "$tags" | while IFS= read -r line; do printf '  %s\n' "$line"; done; else say "  (none)"; fi

info "Starting…"

(
  tmpdir=$(mktemp -d)

  # Cleanup function to restore original venv
  cleanup() {
    info "Restoring original version…"
    if (cd "$original_repo" && source .venv/bin/activate && touch pyproject.toml && make dev >/dev/null 2>&1); then
      ok "Original version restored"
    else
      warn "Failed to restore original version"
    fi
    rm -rf "$tmpdir"
  }

  trap cleanup EXIT
  warn "Working in: $tmpdir"

  # Clone repository
  say "Cloning repository…"
  git clone --no-tags --mirror "$original_repo" "$tmpdir/mirror" >/dev/null
  git clone "$tmpdir/mirror" "$tmpdir/repo" >/dev/null
  cd "$tmpdir/repo"

  git config advice.detachedHead false

  # We'll install each version into our original venv and run perf from there

  # Sanitize ref for branch names/paths
  safe_name() { printf '%s' "$1" | sed 's|[^a-zA-Z0-9._/-]|_|g'; }

  run_make() {
    local cmd=(make "$MAKE_TARGET")
    [[ -n "$CPU_PIN" ]] && cmd=(taskset -c "$CPU_PIN" "${cmd[@]}")
    "${cmd[@]}"
  }

  install_and_benchmark() {
    local ref="$1" kind="$2"
    local sha; sha=$(git rev-parse --short "$ref")

    say ""
    info "Installing $kind: $ref ($sha)…"

    # Check out the version
    git checkout "$ref" >/dev/null 2>&1 || {
      err "✗ Failed to checkout $ref"
      return 1
    }

    # Get commit date for this specific version
    local commit_date; commit_date=$(git log -1 --format='%cI' HEAD)

    # Install this version into our venv and run benchmark from our directory
    if (cd "$original_repo" && source .venv/bin/activate && pip install -e "$tmpdir/repo" >/dev/null 2>&1); then
      info "Benchmarking $kind: $ref ($sha)…"
      if (cd "$original_repo" && source .venv/bin/activate && scripts/perf.sh "$ref" "$commit_date" >/dev/null 2>&1); then
        ok "✓ Complete: $ref"
      else
        err "✗ Benchmark failed: $ref"
      fi
    else
      err "✗ Install failed: $ref"
    fi

    # Go back to tmpdir for next iteration
    cd "$tmpdir/repo"
  }


  # Process tags
  if [[ -n "$tags" ]]; then
    for tag in $tags; do
      install_and_benchmark "$tag" "tag"
    done
  fi

  # Reinstall our original version
  cd "$original_repo"
  info "Reinstalling original version…"
  if source .venv/bin/activate && touch pyproject.toml && make dev >/dev/null 2>&1; then
    ok "Original version restored"
  else
    warn "Failed to restore original version"
  fi

  # Debug: check git state before cleanup
  info "Final git state: $(git rev-parse --short HEAD 2>/dev/null || echo 'UNKNOWN')"
  ok "Performance comparison complete."
)

warn "See: logs/perf/parser/ (including logs/perf/parser/runs.csv) for results."
