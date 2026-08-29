#!/usr/bin/env bash
# chmod +x - executable script
set -euo pipefail
# Start MLX LM server with Qwen3.8-27B (Mac alternative to llama.cpp).
# Usage: bash scripts/run_mlx.sh [mlx-model-id]
# Requires: pip install mlx-lm
MODEL="${1:-mlx-community/Qwen3.8-27B-Instruct-4bit}"
if ! python3 -c "import mlx_lm" 2>/dev/null; then
  echo "mlx_lm not found — pip install mlx-lm" >&2
  exit 1
fi
echo "Starting mlx_lm server: $MODEL"
exec python3 -m mlx_lm.server --model "$MODEL" --port 8080 --host 127.0.0.1
