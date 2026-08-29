#!/usr/bin/env bash
set -euo pipefail
# Health-chat macOS/Linux installer — idempotent.
# - Creates venv in .venv
# - pip installs pyproject
# - Fetches guideline corpus
# - Prints next steps for model download + run
#
# Usage: bash scripts/install.sh

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== health-chat installer (macOS/Linux) =="
echo "root: $ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found — install Python 3.10+ first." >&2
  exit 1
fi

# venv
if [[ ! -d .venv ]]; then
  echo "-> creating .venv"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -U pip wheel -q
echo "-> pip install -e .[dev]"
pip install -e ".[dev]" -q

# guidelines
if [[ -f resources/manifest.json ]]; then
  echo "-> fetching guidelines (missing only)"
  python scripts/fetch_guidelines.py || echo "warning: some fetches failed — see output" >&2
fi

# llama.cpp check (optional)
if ! command -v llama-server >/dev/null 2>&1; then
  echo ""
  echo "NOTE: llama-server not found. Install llama.cpp:"
  echo "  brew install llama.cpp          # macOS"
  echo "  # or build from https://github.com/ggml-org/llama.cpp"
fi

echo ""
echo "== done =="
echo "Next:"
echo "  1) Download Qwen3-27B Q4_K_M GGUF to ./models/ (see docs/MODELS.md) — requires ~18GB RAM"
echo "  2) Start LLM:  llama-server -m models/qwen3-27b-q4_k_m.gguf --port 8080 --ctx-size 8192"
echo "     or MLX on Mac:  bash scripts/run_mlx.sh"
echo "  3) Put lab PDFs in ./data/ (or set DATA_DIR)"
echo "  4) Run app:  DATA_DIR=./data .venv/bin/python server.py"
echo "     Open http://127.0.0.1:8787  (passcode printed on start)"
