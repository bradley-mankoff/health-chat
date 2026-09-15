#!/usr/bin/env bash
# Maintainer-only: regenerate the hash-locked requirements from pyproject.toml.
# Requires uv: brew install uv / winget install astral-sh.uv / pip install uv.
# After refreshing, run the advisory scan (docs/DEPENDENCIES.md) before committing.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
command -v uv >/dev/null 2>&1 || { echo "uv not found — install uv first (brew install uv or pip install uv)" >&2; exit 1; }
echo "-> uv pip compile requirements.txt"
uv pip compile pyproject.toml --universal --python-version 3.10 --generate-hashes -o requirements.txt
echo "-> uv pip compile requirements-dev.txt"
uv pip compile pyproject.toml --extra dev --universal --python-version 3.10 --generate-hashes -o requirements-dev.txt
echo "done — verify: bash scripts/install.sh --dev && .venv/bin/python -m pytest -q"
