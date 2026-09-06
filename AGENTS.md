# health-chat — AGENTS.md

Private, local Q&A over your own lab PDFs grounded in your records and curated guideline excerpts, answered by a local Qwen3.8-27B model with citations — no cloud calls.

## Quick start for agents

```bash
git clone https://github.com/bradley-mankoff/health-chat.git
cd health-chat

# 1) Install (creates .venv, installs deps, fetches guideline excerpts)
bash scripts/install.sh

# 2) Fetch guidelines (already run by install; re-run to update missing only)
.venv/bin/python scripts/fetch_guidelines.py

# 3) model download — Qwen3.8-27B Q4_K_M GGUF (~16.5 GB on disk, ~18 GB resident at 8192 context, needs 32GB RAM — see docs/MODELS.md)
mkdir -p models
curl -L -o models/qwen3.8-27b-q4_k_m.gguf \
  "https://huggingface.co/bartowski/Qwen_Qwen3.8-27B-GGUF/resolve/main/Qwen_Qwen3.8-27B-Q4_K_M.gguf"

# 4) Start LLM (OpenAI-compatible API on 127.0.0.1:8080)
llama-server -m models/qwen3.8-27b-q4_k_m.gguf --port 8080 --ctx-size 8192 --host 127.0.0.1 &
# Mac alternative: bash scripts/run_mlx.sh

# 5) Run app
mkdir -p data
# put lab PDFs in ./data or set DATA_DIR elsewhere
DATA_DIR=./data .venv/bin/python server.py
# open http://127.0.0.1:8787 — passcode printed on start, also in .passcode
```

Environment overrides: `LLM_URL` (default `http://127.0.0.1:8080`), `DATA_DIR` (default `./data`), `HOST` (default `127.0.0.1`), `PORT` (default `8787`).

## API endpoints

All `/api/*` require `Authorization: Bearer <passcode>` (passcode from stdout or `.passcode`).

- `GET /api/health` — index status: file count, chunk count, data_dir, model id.
- `POST /api/index` — rebuild BM25 index from `DATA_DIR` and guideline chunks.
- `POST /api/upload` — multipart upload of PDF(s) to `DATA_DIR`, reindexes, returns per-file parse preview.
- `POST /api/chat` — start chat job: `{question, history}` → `{id}`. Poll `GET /api/chat/{id}` for streamed result. Grounded in retrieved record chunks + triaged guideline chunks; cites short names.
- `GET /api/chat/{job_id}` — poll job status/result.
- `GET /api/labs` — parsed structured labs `{name, value, unit, flag, range}`.
- `GET /api/guidelines` — guideline domain chunk counts.

Example:

```bash
PASS=$(cat .passcode)
curl -H "Authorization: Bearer $PASS" http://127.0.0.1:8787/api/health
curl -H "Authorization: Bearer $PASS" -X POST http://127.0.0.1:8787/api/index
curl -H "Authorization: Bearer $PASS" -F "file=@lab.pdf" http://127.0.0.1:8787/api/upload
```

## Guideline fetcher

Public repo does not redistribute verbatim guideline text. `resources/manifest.json` lists canonical URLs and short citation names; `scripts/fetch_guidelines.py` downloads excerpts to `resources/<domain>/*.txt` on the user's machine. Install runs it for missing files only; use `--force` to re-download, `--dry-run` to inspect. Fetched `*.txt` are gitignored — see `resources/README.md`.

## Minimum specs

Qwen3.8-27B only — 27B Q4_K_M requires 32GB RAM or 16GB VRAM (~18 GB resident at 8192 context). Smaller models are untested for grounding quality. See `docs/HARDWARE.md` and `docs/MODELS.md`.

## Security and disclaimer

Local-only by default (`127.0.0.1:8787`, LLM at `127.0.0.1:8080`), no telemetry or web search. Passcode is a local shared secret, not HIPAA auth; no encryption at rest. See [SECURITY.md](SECURITY.md) for privacy model and [DISCLAIMER.md](DISCLAIMER.md) — this software is for information only, not medical advice.

Further docs: [README.md](README.md), [docs/INSTALL.md](docs/INSTALL.md), [docs/HARDWARE.md](docs/HARDWARE.md), [docs/MODELS.md](docs/MODELS.md).
