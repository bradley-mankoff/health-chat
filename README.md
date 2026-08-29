# health-chat — private lab-results chat (labs-only POC)

<!-- screenshot placeholder — replace before publish:
     ![health-chat UI](docs/screenshot.png)
     Screenshot should show the chat + lab-parsed table with citations.
-->

> **Not medical advice.** For information only — see [DISCLAIMER.md](DISCLAIMER.md). See [SECURITY.md](SECURITY.md) for privacy model (local-only, loopback by default, no cloud).

Private, local Q&A over **your own lab PDFs**, grounded in curated guideline excerpts. No data leaves your machine in v1. The local model (Qwen3.8-27B via llama.cpp/MLX) answers only from your records + retrieved guidelines, with citations.

**v1 scope:** Labs only (Quest PDFs best), ~6→15 lab domains, fully local (no web search), no diagnosis — see doctor.

---

## What it does / doesn't do

- ✅ Parses Quest lab panels into structured `{name,value,unit,flag,range}` without LLM; falls back to raw chunks if parse misses
- ✅ BM25 retrieval over your records + per-domain guideline triage
- ✅ Cites guideline short names (e.g. “per ARUP FSH Test Directory”)
- ❌ Does NOT diagnose or recommend treatment — hedges with “only your doctor can diagnose”
- ❌ Does NOT cover every lab in v1 (BMP/CMP/lipids/A1c/Vit D added via manifest — see `resources/manifest.json`)
- ❌ Does NOT search the web in v1 (planned v2, PHI-sanitized)

---

## Hardware

**Requires 32GB RAM or 16GB VRAM** for Qwen3.8-27B Q4_K_M (~16.5 GB). No “fits on many machines” claim in v1 — see `docs/HARDWARE.md` and `docs/MODELS.md`. MLX faster on Apple Silicon.

| Machine | Can run 27B Q4? |
|---------|-----------------|
| 32GB MacBook Pro (M1 Max/Pro) | Yes |
| 16GB Mac / 8GB Air | No (v1 unsupported) |

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

Windows: `powershell -ExecutionPolicy Bypass -File scripts\install.ps1`

MLX (Mac alt): `bash scripts/run_mlx.sh` (needs `pip install mlx-lm`)

Short form + troubleshooting: see [docs/INSTALL.md](docs/INSTALL.md). Full docs: [docs/HARDWARE.md](docs/HARDWARE.md), [docs/MODELS.md](docs/MODELS.md), [SECURITY.md](SECURITY.md), [DISCLAIMER.md](DISCLAIMER.md).

---

## Uploading labs

Drag-and-drop in the UI (after `UX-1` lands) or drop PDFs in `DATA_DIR` then hit **Reindex**. Parser is Quest-optimized — other labs still searchable via raw chunks but show “unparsed” in the preview table.

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
# if you used a custom DATA_DIR, delete that folder too
```

Browsing data: chat history is in your browser's site storage — clear site data for `http://127.0.0.1:8787` to wipe it. See [SECURITY.md](SECURITY.md) and [DISCLAIMER.md](DISCLAIMER.md) for privacy scope.

---

## For Agents

Agents: see [AGENTS.md](AGENTS.md) — one-page quick start (git clone, install, model download, run) and API endpoints. Also see `llms.txt` for the doc index.

---

## Development

```bash
pytest -q
python scripts/fetch_guidelines.py --dry-run
```

See `handoff.md` for the locked open-source hardening plan and ticket graph.

---

## License

MIT — see `LICENSE`. Guideline excerpts fetched on install are copyright their publishers; short excerpts with attribution. This software is not medical advice — see [DISCLAIMER.md](DISCLAIMER.md).
