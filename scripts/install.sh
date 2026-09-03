#!/usr/bin/env bash
# chmod +x - executable script
set -euo pipefail
# Health-chat macOS/Linux installer — idempotent.
# - Creates venv in .venv
# - pip installs pyproject
# - Fetches guideline corpus
# - Prints next steps for model download + run
#
# Usage: bash scripts/install.sh [--dev]

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== health-chat installer (macOS/Linux) =="
echo "root: $ROOT"

# --- RAM guard (Qwen3.8-27B Q4) ---
# Detects total RAM via sysctl (macOS), /proc/meminfo (Linux), or free.
# Prints "Detected X GB RAM — 27B Q4 needs ~18GB (32GB recommended)" and
# warns at <24GB / errors at <18GB but never blocks the installer (warn-only).
RAM_GB=""
if command -v sysctl >/dev/null 2>&1; then
  _mem_bytes="$(sysctl -n hw.memsize 2>/dev/null || true)"
  if [[ -n "${_mem_bytes:-}" && "${_mem_bytes}" =~ ^[0-9]+$ ]]; then
    RAM_GB=$(( _mem_bytes / 1024 / 1024 / 1024 ))
  fi
fi
if [[ -z "${RAM_GB:-}" ]] && [[ -r /proc/meminfo ]]; then
  _mem_kb="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo 2>/dev/null || true)"
  if [[ -n "${_mem_kb:-}" && "${_mem_kb}" =~ ^[0-9]+$ ]]; then
    RAM_GB=$(( _mem_kb / 1024 / 1024 ))
  fi
fi
if [[ -z "${RAM_GB:-}" ]] && command -v free >/dev/null 2>&1; then
  _mem_mb="$(free -m 2>/dev/null | awk '/^Mem:/ {print $2}' || true)"
  if [[ -n "${_mem_mb:-}" && "${_mem_mb}" =~ ^[0-9]+$ ]]; then
    RAM_GB=$(( (_mem_mb + 1023) / 1024 ))
  fi
fi
if [[ -n "${RAM_GB:-}" ]]; then
  echo "Detected ${RAM_GB} GB RAM — 27B Q4 needs ~18GB (32GB recommended)"
  if (( RAM_GB < 18 )); then
    echo "ERROR: Qwen3.8-27B Q4 requires ~18GB RAM; you have ${RAM_GB}GB — see docs/HARDWARE.md; installer will continue but model will OOM" >&2
  elif (( RAM_GB < 24 )); then
    echo "WARNING: <24GB RAM detected (${RAM_GB}GB) — 27B Q4 may be tight; 32GB recommended. See docs/HARDWARE.md" >&2
  fi
else
  echo "WARNING: could not detect total RAM — 27B Q4 needs ~18GB (32GB recommended); see docs/HARDWARE.md" >&2
fi
# --- end RAM guard ---
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found — install Python 3.10+ first." >&2
  exit 1
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "Python 3.10+ required — found $(python3 --version 2>&1)." >&2
  exit 1
fi

# venv
if [[ ! -d .venv ]]; then
  echo "-> creating .venv"
  python3 -m venv .venv
fi
VENV_PY="$ROOT/.venv/bin/python"
"$VENV_PY" -m pip install -U pip wheel -q
if [[ "${1:-}" == "--dev" ]]; then
  echo "-> pip install -e .[dev]"
  "$VENV_PY" -m pip install -e ".[dev]" -q
else
  echo "-> pip install -e ."
  "$VENV_PY" -m pip install -e . -q
fi

# guidelines
if [[ -f resources/manifest.json ]]; then
  echo "-> fetching guidelines (missing only)"
  "$VENV_PY" scripts/fetch_guidelines.py || echo "warning: some fetches failed — see output" >&2
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
echo "  1) Download Qwen3.8-27B Q4_K_M GGUF to ./models/ (see docs/MODELS.md) — requires ~18GB RAM"
echo "  2) Start LLM:  llama-server -m models/qwen3.8-27b-q4_k_m.gguf --port 8080 --ctx-size 8192"
echo "     or MLX on Mac:  bash scripts/run_mlx.sh"
echo "  3) Put lab PDFs in ./data/ (or set DATA_DIR)"
echo "  4) Run app:  DATA_DIR=./data .venv/bin/python server.py"
echo "     Open http://127.0.0.1:8787  (passcode printed on start)"
