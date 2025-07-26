#!/usr/bin/env bash

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
source .venv/bin/activate

if command -v uv >/dev/null 2>&1; then
    export PIP="uv pip"
else
    export PIP="python3 -m pip"
fi
