#!/bin/sh
# The whole suite plus lint for mcp-art-lab: CLAUDE_VERIFY_CMD, the stop hook and CI run this.
# Each check on its own line, so `set -e` stops at the first failure.
# `--locked` fails when uv.lock is out of date with pyproject.toml instead of rewriting it.
set -eu
cd "$(dirname "$0")/.."

uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest

echo VERIFY OK
