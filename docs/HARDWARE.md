# Hardware

## Model

Health-chat runs **Qwen3.8-27B** (GGUF `Q4_K_M` ≈ **16.5 GB** on disk, ≈ **18 GB RAM** resident at 8192 context). Only this model is validated — smaller tiers fit but have not been validated for grounding quality.

## Minimum specs

- **RAM:** 32 GB unified/system RAM, or 16 GB VRAM with GPU offload
- **Disk:** ~20 GB free (model + venv + guidelines)
- **OS:** macOS 13+, Windows 10/11, or Linux (x64/ARM64)
- **Python:** 3.10+

| Component | Minimum | Notes |
|---|---|---|
| RAM | 32 GB | ~18 GB resident at 8192 context; installer warns below 32 GB |
| VRAM | 16 GB | alternative to 32 GB RAM with GPU offload |
| Disk | ~20 GB free | ~16.5 GB model + venv + guidelines |
| OS | macOS 13+, Windows 10/11, or Linux | x64/ARM64 |
| Python | 3.10+ | |
| Model | Qwen3.8-27B Q4_K_M | ~16.5 GB on disk, ~18 GB resident at 8192 context |

The installer checks RAM and warns if you have less than 32 GB — the model will OOM below ~18 GB resident at 8192 context.

## Engine

- **Primary:** `llama.cpp` (`llama-server`) — cross-platform, runs GGUFs on CPU or GPU.
- **Mac alternative:** `MLX` (`mlx_lm` server) — faster on Apple Silicon, same Qwen3.8-27B weights converted to MLX format. See `scripts/run_mlx.sh`.

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
