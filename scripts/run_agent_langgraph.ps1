# Start LangGraph agent for Agent Chat UI (Windows)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

if (-not (Test-Path ".\.venv-langgraph\Scripts\langgraph.exe")) {
  Write-Host "Creating .venv-langgraph ..."
  uv venv .venv-langgraph
  uv pip install --python .venv-langgraph -e "."
  uv pip install --python .venv-langgraph "langgraph-cli[inmem]"
}

if (-not (Test-Path ".\langgraph.env")) {
  Copy-Item ".\langgraph.env.example" ".\langgraph.env"
  Write-Host "Created langgraph.env from example — fill SILICON_KEY / LLM settings."
}

Write-Host "Starting LangGraph on http://127.0.0.1:2024 (graph id: agent)"
& .\.venv-langgraph\Scripts\langgraph.exe dev --port 2024 --no-browser
