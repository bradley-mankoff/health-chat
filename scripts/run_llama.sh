#!/usr/bin/env bash
# chmod +x - executable script
set -euo pipefail
# Start llama-server with Qwen3.8-27B Q4_K_M GGUF (authenticated).
# Usage: bash scripts/run_llama.sh [path/to/gguf]
# Shares LLM_API_KEY with health-chat (server.py): env wins, else
# .llm_api_key next to server.py, else generated and saved there (0600).
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
KEY_FILE="$ROOT/.llm_api_key"
if [[ -n "${LLM_API_KEY:-}" ]]; then
  KEY="$LLM_API_KEY"
elif [[ -f "$KEY_FILE" ]]; then
  KEY="$(cat "$KEY_FILE")"
else
  KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  printf '%s' "$KEY" > "$KEY_FILE"
  chmod 600 "$KEY_FILE"
  echo "Generated LLM API key in $KEY_FILE — health-chat server.py reuses it" >&2
fi
export LLM_API_KEY="$KEY"
echo "Starting llama-server: $MODEL (authenticated, loopback only)"
exec llama-server -m "$MODEL" --port 8080 --ctx-size 8192 --host 127.0.0.1 --api-key "$KEY"
