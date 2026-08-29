# health-chat Windows installer
# Usage: powershell -ExecutionPolicy Bypass -File scripts\install.ps1
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
Write-Host "== health-chat installer (Windows) =="
Write-Host "root: $Root"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Error "python not found — install Python 3.10+ and add to PATH."
  exit 1
}
if (-not (Test-Path ".venv")) {
  Write-Host "-> creating .venv"
  python -m venv .venv
}
& .\.venv\Scripts\Activate.ps1
python -m pip install -U pip wheel -q
Write-Host "-> pip install -e .[dev]"
pip install -e ".[dev]" -q

if (Test-Path "resources\manifest.json") {
  Write-Host "-> fetching guidelines (missing only)"
  python scripts\fetch_guidelines.py
  if ($LASTEXITCODE -ne 0) { Write-Host "warning: some fetches failed — see output" }
}

if (-not (Get-Command llama-server -ErrorAction SilentlyContinue)) {
  Write-Host ""
  Write-Host "NOTE: llama-server not found. Install llama.cpp:"
  Write-Host "  winget install llama.cpp  # or build from https://github.com/ggml-org/llama.cpp"
}

Write-Host ""
Write-Host "== done =="
Write-Host "Next:"
Write-Host "  1) Download Qwen3-27B Q4_K_M GGUF to .\models\ (see docs\MODELS.md) — requires ~18GB RAM"
Write-Host "  2) Start LLM:  llama-server -m models\qwen3-27b-q4_k_m.gguf --port 8080 --ctx-size 8192"
Write-Host "  3) Put lab PDFs in .\data\ (or set DATA_DIR)"
Write-Host "  4) Run app:  `$env:DATA_DIR='./data'; .\.venv\Scripts\python.exe server.py"
Write-Host "     Open http://127.0.0.1:8787  (passcode printed on start)"
