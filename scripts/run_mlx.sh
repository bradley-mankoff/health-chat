#!/usr/bin/env bash
# chmod +x - executable script
set -euo pipefail
# Start MLX LM server (default: Qwen3.8-27B; testing: MiniCPM5-2B — see docs/MODELS.md).
# Usage: bash scripts/run_mlx.sh [mlx-model-id]  # e.g. openbmb/MiniCPM5-2B-MLX for fast smoke
# Requires: .venv/bin/python -m pip install mlx-lm
MODEL="${1:-mlx-community/Qwen3.8-27B-Instruct-4bit}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
if [[ ! -x "$PY" ]]; then PY="python3"; fi
if ! "$PY" -c "import mlx_lm" 2>/dev/null; then
  echo "mlx_lm not found — $PY -m pip install mlx-lm" >&2
  exit 1
fi
echo "Starting mlx_lm server: $MODEL"
exec "$PY" -m mlx_lm.server --model "$MODEL" --port 8080 --host 127.0.0.1
