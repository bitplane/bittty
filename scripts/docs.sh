#!/usr/bin/bash

source .venv/bin/activate

set -e

pushd src
pydoc-markdown -p "$1" > ../docs/pydoc.md
popd

mkdocs build
mkdocs gh-deploy
