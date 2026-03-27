Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function U([int[]]$codes) {
  return -join ($codes | ForEach-Object { [char]$_ })
}

# Force UTF-8 for Python output
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

Set-Location -LiteralPath $PSScriptRoot

# Ensure PYTHONPATH contains repo root
if ($env:PYTHONPATH) { $env:PYTHONPATH = "$PSScriptRoot;$env:PYTHONPATH" } else { $env:PYTHONPATH = "$PSScriptRoot" }

# Pick venv first, then venv_skills
$pyexe = $null
$venvPy = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
$skillsPy = Join-Path $PSScriptRoot "venv_skills\Scripts\python.exe"
if (Test-Path -LiteralPath $venvPy) { $pyexe = $venvPy }
elseif (Test-Path -LiteralPath $skillsPy) { $pyexe = $skillsPy }

if (-not $pyexe) {
  Write-Host "[ERROR] venv or venv_skills not found."
  exit 1
}

# Ensure python-dotenv exists (required to load .env)
& $pyexe -c "import dotenv" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
  Write-Host "[ERROR] python-dotenv is not installed."
  Write-Host ("Run: {0} -m pip install python-dotenv" -f $pyexe)
  exit 1
}

# Ensure streamlit exists
& $pyexe -c "import streamlit" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
  Write-Host "[ERROR] streamlit is not installed."
  Write-Host ("Run: {0} -m pip install -r requirements.txt" -f $pyexe)
  exit 1
}

# Chinese banner (ASCII-only script; text generated from code points)
$title = U 0x6E38,0x620F,0x7F16,0x5267,0x5DE5,0x4F5C,0x53F0
$openBrowser = (U 0x6D4F,0x89C8,0x5668,0x6253,0x5F00) + ": http://localhost:8501"
$stopTip = (U 0x505C,0x6B62,0x670D,0x52A1,0x8BF7,0x5728,0x672C,0x7A97,0x53E3,0x6309) + " Ctrl+C"

Write-Host ""
Write-Host "========================================"
Write-Host ("  {0}" -f $title)
Write-Host ("  {0}" -f $openBrowser)
Write-Host ("  {0}" -f $stopTip)
Write-Host "========================================"
Write-Host ""

$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path -LiteralPath $envFile) {
  & $pyexe -m dotenv -f ".env" run -- $pyexe -m streamlit run "src\ui\streamlit_app.py" --server.address=localhost --browser.gatherUsageStats=false
} else {
  & $pyexe -m streamlit run "src\ui\streamlit_app.py" --server.address=localhost --browser.gatherUsageStats=false
}

Write-Host ""
Write-Host ("[EXITED] Streamlit exit code: {0}" -f $LASTEXITCODE)
