# health-chat Windows installer
# chmod +x - executable script
# Usage: powershell -ExecutionPolicy Bypass -File scripts\install.ps1
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
Write-Host "== health-chat installer (Windows) =="
Write-Host "root: $Root"

# --- RAM guard (Qwen3.8-27B Q4) ---
# Detects total RAM via Win32_PhysicalMemory (Windows); falls back to
# Win32_ComputerSystem and, for pwsh on macOS/Linux, sysctl / /proc/meminfo.
# Prints "Detected X GB RAM — 27B Q4 needs ~18GB (32GB recommended)" and
# warns at <24GB / errors at <18GB but never blocks the installer (warn-only).
$RamGb = $null
try {
  $cimMem = Get-CimInstance Win32_PhysicalMemory -ErrorAction SilentlyContinue | Measure-Object -Property Capacity -Sum
  if ($cimMem -and $cimMem.Sum) {
    $RamGb = [math]::Floor($cimMem.Sum / 1GB)
  }
  if (-not $RamGb) {
    $cs = Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue
    if ($cs -and $cs.TotalPhysicalMemory) {
      $RamGb = [math]::Floor($cs.TotalPhysicalMemory / 1GB)
    }
  }
} catch { $RamGb = $null }
# Fallback for pwsh on macOS/Linux (non-Windows) — ensures this 32GB machine still reports correctly
if (-not $RamGb) {
  try {
    if (Test-Path "/proc/meminfo") {
      $m = Select-String -Path "/proc/meminfo" -Pattern "^MemTotal:\s+(\d+)" | Select-Object -First 1
      if ($m -and $m.Matches.Groups[1].Value) {
        $kb = [long]$m.Matches.Groups[1].Value
        $RamGb = [math]::Floor($kb / 1024 / 1024)
      }
    } elseif (Get-Command sysctl -ErrorAction SilentlyContinue) {
      $out = & sysctl -n hw.memsize 2>$null
      if ($out -match "^\d+$") {
        $RamGb = [math]::Floor([long]$out / 1GB)
      }
    } elseif (Get-Command free -ErrorAction SilentlyContinue) {
      $freeOut = & free -m 2>$null | Select-String "^Mem:"
      if ($freeOut) {
        $parts = $freeOut.Line -split "\s+"
        if ($parts.Count -ge 2 -and $parts[1] -match "^\d+$") {
          $RamGb = [math]::Floor([long]$parts[1] / 1024)
        }
      }
    }
  } catch { $RamGb = $null }
}
if ($RamGb) {
  Write-Host "Detected $RamGb GB RAM — 27B Q4 needs ~18GB (32GB recommended)"
  if ($RamGb -lt 18) {
    Write-Host "ERROR: Qwen3.8-27B Q4 requires ~18GB RAM; you have ${RamGb}GB — see docs/HARDWARE.md; installer will continue but model will OOM" -ForegroundColor Red
  } elseif ($RamGb -lt 24) {
    Write-Host "WARNING: <24GB RAM detected (${RamGb}GB) — 27B Q4 may be tight; 32GB recommended. See docs/HARDWARE.md" -ForegroundColor Yellow
  }
} else {
  Write-Host "WARNING: could not detect total RAM — 27B Q4 needs ~18GB (32GB recommended); see docs/HARDWARE.md" -ForegroundColor Yellow
}
# --- end RAM guard ---
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
Write-Host "  1) Download Qwen3.8-27B Q4_K_M GGUF to .\models\ (see docs\MODELS.md) — requires ~18GB RAM"
Write-Host "  2) Start LLM:  llama-server -m models\qwen3.8-27b-q4_k_m.gguf --port 8080 --ctx-size 8192"
Write-Host "  3) Put lab PDFs in .\data\ (or set DATA_DIR)"
Write-Host "  4) Run app:  `$env:DATA_DIR='./data'; .\.venv\Scripts\python.exe server.py"
Write-Host "     Open http://127.0.0.1:8787  (passcode printed on start)"
