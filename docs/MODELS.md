# Models — Qwen3-27B (v1)

## Default: Qwen3-27B Q4_K_M GGUF

- **Source:** Qwen3-27B Instruct, quantized `Q4_K_M`
- **File:** ~16.5 GB, e.g. `qwen3-27b-instruct-q4_k_m.gguf`
- **RAM:** ~18 GB resident at 4096 context
- **Where to get:** Hugging Face — search `Qwen3-27B GGUF Q4_K_M` (e.g. `unsloth` or `bartowski` quants). Always verify SHA256.

```bash
# Example (replace URL with your chosen quant)
curl -L -o models/qwen3-27b-q4_k_m.gguf \
  "https://huggingface.co/bartowski/Qwen_Qwen3-27B-GGUF/resolve/main/Qwen_Qwen3-27B-Q4_K_M.gguf"

# llama.cpp
./llama-server -m models/qwen3-27b-q4_k_m.gguf --port 8080 --ctx-size 8192

# MLX (Mac) — convert or download MLX-converted weights, then:
mlx_lm.server --model mlx-community/Qwen3-27B-Instruct-4bit --port 8080
```

Configure health-chat via `LLM_URL` (default `http://127.0.0.1:8080`).

## v1 scope

- Only 27B is validated. 7B/14B may work but are **unsupported** — grounding fidelity will differ and is not tested.
- Future: installer will detect RAM and suggest tier (7B for 8GB, 14B for 16GB, 27B for 32GB). Not in v1.

## Why Qwen3-27B?

Tested balance of reasoning + retrieval grounding + fits on a single prosumer machine (32GB). Smaller models hallucinate more on guideline citations; larger (70B+) needs datacenter.

## Verify

```bash
curl http://127.0.0.1:8080/v1/models | jq .
```
