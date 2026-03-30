Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $ProjectRoot "venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Py)) {
  throw "未找到 venv Python：$Py"
}

$env:VECTOR_EMBED_MODEL = (Join-Path $ProjectRoot "models\bge-small-zh-v1.5")
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"

Write-Host "Python:" (& $Py -c "import sys; print(sys.executable)")
Write-Host "VECTOR_EMBED_MODEL=$env:VECTOR_EMBED_MODEL"

Write-Host ""
Write-Host "=== retrieve_context('林夕', top_k=3) ==="
& $Py -c "from src.tools.vector_retriever import retrieve_context; print(retrieve_context('林夕', top_k=3))"

Write-Host ""
Write-Host "=== vector_search('query=林夕|top_k=3') ==="
& $Py -c "from src.tools.vector_tools import vector_search; print(vector_search('query=林夕|top_k=3'))"

