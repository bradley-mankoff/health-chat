#!/usr/bin/env bash
# chmod +x - executable script
set -euo pipefail
# Start llama-server with Qwen3.8-27B Q4_K_M GGUF.
# Usage: bash scripts/run_llama.sh [path/to/gguf]
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODEL="${1:-$ROOT/models/qwen3.8-27b-q4_k_m.gguf}"
if [[ ! -f "$MODEL" ]]; then
  echo "GGUF not found: $MODEL" >&2
  echo "Download Qwen3.8-27B Q4_K_M to that path — see docs/MODELS.md" >&2
  exit 1
fi
if ! command -v llama-server >/dev/null 2>&1; then
  echo "llama-server not found — install llama.cpp (brew install llama.cpp)" >&2
  exit 1
fi
echo "Starting llama-server: $MODEL"
exec llama-server -m "$MODEL" --port 8080 --ctx-size 8192 --host 127.0.0.1
