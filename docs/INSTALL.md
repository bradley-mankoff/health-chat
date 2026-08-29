# Install — short form

> Full hardware/model details: [HARDWARE.md](HARDWARE.md), [MODELS.md](MODELS.md). Privacy model: [../SECURITY.md](../SECURITY.md).

## Mac / Linux (one-liner)

```bash
bash scripts/install.sh
```

What it does: creates `.venv`, `pip install -e .[dev]`, fetches guideline excerpts per `resources/manifest.json` (missing only). Idempotent — safe to re-run.

Then:

```bash
# Qwen3.8-27B Q4_K_M — ~16.5 GB on disk, ~18 GB resident at 8192 context, needs 32GB RAM — see MODELS.md
mkdir -p models
curl -L -o models/qwen3.8-27b-q4_k_m.gguf "https://huggingface.co/bartowski/Qwen_Qwen3.8-27B-GGUF/resolve/main/Qwen_Qwen3.8-27B-Q4_K_M.gguf"
llama-server -m models/qwen3.8-27b-q4_k_m.gguf --port 8080 --ctx-size 8192 --host 127.0.0.1 &
#    or on Apple Silicon (faster): bash scripts/run_mlx.sh
mkdir -p data && cp ~/Downloads/*.pdf data/
DATA_DIR=./data python server.py
# open http://127.0.0.1:8787 — passcode printed in terminal
```

## Windows (one-liner)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install.ps1
```

Same steps as above after install (use `.\models\...`, `$env:DATA_DIR='./data'; .\.venv\Scripts\python.exe server.py`). See `scripts/install.ps1` for details.

## Uninstall / remove data

See [README.md — How to uninstall](../README.md#how-to-uninstall--remove-data) — `rm -rf .venv data models resources/cache` + `rm resources/*/*.txt`, clear browser site data for `127.0.0.1:8787`.

## Troubleshooting

- `llama-server: command not found` → install llama.cpp: `brew install llama.cpp` (Mac) or build from https://github.com/ggml-org/llama.cpp
- `python3 not found` → install Python 3.10+
- OOM with 27B → you need 32GB RAM / 16GB VRAM (~18 GB resident at 8192 context); see HARDWARE.md — v1 is 27B-only
- Guidelines failed to fetch → re-run `python scripts/fetch_guidelines.py` or `--dry-run` to inspect URLs in `resources/manifest.json`
