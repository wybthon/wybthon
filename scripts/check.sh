#!/usr/bin/env bash
# Run the same checks as ci.yml, in the same order. If this script is green,
# CI should be green too.
set -euo pipefail

cd "$(dirname "$0")/.."

uv sync --locked --group dev

uv run ruff check .
uv run black --check .
uv run mypy
uv run pytest -q --cov=wybthon --cov-branch --cov-report=term-missing --cov-fail-under=45
