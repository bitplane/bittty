#!/usr/bin/env bash

source .venv/bin/activate

pytest -vv --asyncio-mode=auto .
