# health-chat — private lab-results chat

<!-- screenshot placeholder — replace before publish:
     ![health-chat UI](docs/screenshot.png)
-->

> **Not medical advice.** For information only — see [DISCLAIMER.md](DISCLAIMER.md). See [SECURITY.md](SECURITY.md) for privacy model.

Private, local Q&A over **your own lab PDFs**, grounded in curated guideline excerpts. No data leaves your machine. The local model (Qwen3.8-27B via llama.cpp/MLX) answers only from your records + retrieved guidelines, with citations.

Robust and private — **labs only** for now. Upload a lab PDF, get structured values and plain-language context from trusted sources. See your doctor for diagnosis or treatment decisions.

---

## What it does / doesn't do

- ✅ Parses Quest lab panels into structured `{name,value,unit,flag,range}` without LLM; falls back to raw chunks if parse misses
- ✅ Retrieval over your records + per-domain guideline triage, cites short names (e.g. “per ARUP FSH Test Directory”)
- ✅ Fully local — no cloud calls, no telemetry
- ❌ Does NOT diagnose or recommend treatment — hedges with “only your doctor can diagnose”
- ❌ Labs only — not a general health chatbot; no web search

---

## Minimum specs

- **Model:** Qwen3.8-27B Q4_K_M — ~16.5 GB on disk, ~18 GB RAM resident
- **RAM:** **32 GB RAM** or **16 GB VRAM** with GPU offload
- **Engine:** `llama.cpp` (`llama-server`) cross-platform; `MLX` faster on Apple Silicon — see `docs/HARDWARE.md` and `docs/MODELS.md`

If you have less than 32 GB, the model will OOM — the installer warns you.

---

## Quick start (Mac / Linux)

```bash
bash scripts/install.sh          # venv + deps + fetch guidelines
# Download Qwen3.8-27B Q4_K_M GGUF to ./models/ — see docs/MODELS.md
llama-server -m models/qwen3.8-27b-q4_k_m.gguf --port 8080 --ctx-size 8192 &
mkdir -p data && cp ~/Downloads/*.pdf data/
DATA_DIR=./data python server.py
# open http://127.0.0.1:8787 — passcode printed in terminal
```

Windows: `powershell -ExecutionPolicy Bypass -File scripts/install.ps1`

MLX (Mac alt): `bash scripts/run_mlx.sh` (needs `pip install mlx-lm`)

See [docs/INSTALL.md](docs/INSTALL.md) for short-form install, `docs/HARDWARE.md` for specs, `docs/MODELS.md` for model download.

---

## Uploading labs

Drag-and-drop in the UI or drop PDFs in `DATA_DIR` then hit **Reindex**. Parser is Quest-optimized — other labs remain searchable via raw chunks and show “unparsed” in the preview table.

---

## How to uninstall / remove data

Health-chat is local-only — no account or cloud data. To remove:

```bash
# stop the servers (Ctrl-C) then:
rm -rf .venv/ data/ models/
rm -f .passcode
# remove fetched guideline excerpts (keeps manifest):
rm -rf resources/cache/
rm -f resources/*/*.txt
```

Browsing data: chat history is in your browser's site storage — clear site data for `http://127.0.0.1:8787` to wipe it.

---

## For Agents

Agents: see [AGENTS.md](AGENTS.md) — one-page quick start (clone, install, model download, run) and API endpoints. Also see `llms.txt` for the doc index.

---

## Development

```bash
pytest -q
python scripts/fetch_guidelines.py --dry-run
```

---

## License

MIT — see `LICENSE`. Guideline excerpts fetched on install are copyright their publishers; short excerpts with attribution. This software is not medical advice — see [DISCLAIMER.md](DISCLAIMER.md).
