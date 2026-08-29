# Hardware Requirements

## v1: Qwen3-27B only

Health-chat is spec'd around **Qwen3-27B** (GGUF `Q4_K_M` ≈ **16.5 GB** on disk, ≈ **18 GB RAM** resident with typical context). This is the model the prompt and grounding were tested against. Smaller tiers are **not** officially supported in v1 — they fit but have not been validated for grounding quality.

| Machine | RAM / VRAM | Can run 27B Q4? | Notes |
|---------|------------|-----------------|-------|
| MacBook Pro 14/16" (M1 Max/Pro, 32GB) | 32GB unified | **Yes** ✅ | Recommended. Use MLX or llama.cpp. |
| MacBook Air / 16GB Mac | 16GB | **No** — will OOM | Wait for future 14B support or upgrade. |
| Windows/Linux desktop | 32GB RAM + GPU | **Yes** ✅ | Needs llama.cpp with GPU offload or 32GB RAM. |
| 8GB laptop | 8GB | **No** | Not supported in v1. |

> **No "fits on many hardware" claim.** If you have <32GB RAM (or <16GB VRAM with GPU offload), v1 will not run the default model. See `docs/MODELS.md` for alternatives and future tiers.

## Engine

- **Primary:** `llama.cpp` (`llama-server`) — cross-platform, runs GGUFs on CPU or GPU.
- **Mac alternative:** `MLX` (`mlx_lm` server) — faster on Apple Silicon, same Qwen3-27B weights converted to MLX format. See `scripts/run_mlx.sh`.

Both expose an OpenAI-compatible API at `LLM_URL` (default `http://127.0.0.1:8080`).

## Quick check

```bash
# macOS
system_profiler SPHardwareDataType | grep Memory
# Linux
free -h
# Windows (PowerShell)
Get-CimInstance Win32_PhysicalMemory | Measure-Object -Property capacity -Sum
```

If total < 24GB, do not attempt 27B Q4. File a feature request for smaller-model support.
