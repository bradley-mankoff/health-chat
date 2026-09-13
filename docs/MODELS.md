# Models — Qwen3.8-27B (v1)

## Default: Qwen3.8-27B Q4_K_M GGUF

- **Source:** Qwen3.8-27B Instruct, quantized `Q4_K_M`
- **File:** ~16.5 GB, e.g. `qwen3.8-27b-instruct-q4_k_m.gguf`
- **RAM:** ~18 GB resident at 8192 context — requires 32 GB RAM or 16 GB VRAM
- **Where to get:** Hugging Face — search `Qwen3.8-27B GGUF Q4_K_M` (e.g. `unsloth` or `bartowski` quants). Always verify SHA256.

```bash
mkdir -p models
curl -L -o models/qwen3.8-27b-q4_k_m.gguf \
  "https://huggingface.co/bartowski/Qwen_Qwen3.8-27B-GGUF/resolve/main/Qwen_Qwen3.8-27B-Q4_K_M.gguf"

# llama.cpp (authenticated — supported path)
bash scripts/run_llama.sh
# equivalent: llama-server -m models/qwen3.8-27b-q4_k_m.gguf --port 8080 --ctx-size 8192 --host 127.0.0.1 --api-key "$LLM_API_KEY"

# MLX (Mac) — convert or download MLX-converted weights, then:
mlx_lm.server --model mlx-community/Qwen3.8-27B-Instruct-4bit --port 8080
# NOTE: mlx_lm.server has no --api-key option (unauthenticated). Health-chat
# refuses to send records to endpoints that accept anonymous requests —
# prefer scripts/run_llama.sh for real records.
```

Configure health-chat via `LLM_URL` (default `http://127.0.0.1:8080`, loopback only).

## LLM authentication (`LLM_API_KEY`)

Prompts contain PHI, so health-chat authenticates its local LLM endpoint with a
shared secret before any records are sent:

- `scripts/run_llama.sh` uses `LLM_API_KEY` env if set, else `.llm_api_key`
  (repo root, `0600`), else generates and saves one — and passes it as
  `llama-server --api-key`.
- `server.py` loads the same value (`LLM_API_KEY` env → `.llm_api_key` →
  generate) and sends `Authorization: Bearer <key>` on model discovery
  (`GET /v1/models`) and chat (`POST /v1/chat/completions`).
- Before each chat, health-chat probes `GET /v1/models` with the key (must
  return `200`) and without it (must return `401`/`403`). If the endpoint
  rejects the key or accepts anonymous requests, no prompt is sent and the
  job reports an actionable identity error (possible impostor on loopback).
- Keep `LLM_URL` on loopback (`127.0.0.1`). A non-loopback `LLM_URL` prints a
  startup warning.

## v1 scope

- Only 27B is validated. 7B/14B may work but are **unsupported** — grounding fidelity will differ and is not tested.
- Future: installer will detect RAM and suggest tier (7B for 8GB, 14B for 16GB, 27B for 32GB). Not in v1.

## Why Qwen3.8-27B?

Tested balance of reasoning + retrieval grounding + fits on a single prosumer machine (32GB). Smaller models hallucinate more on guideline citations; larger (70B+) needs datacenter.

## Verify

```bash
curl -H "Authorization: Bearer $LLM_API_KEY" http://127.0.0.1:8080/v1/models | jq .
# anonymous probe must be rejected (proves --api-key is enforced):
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/v1/models  # expect 401
```
