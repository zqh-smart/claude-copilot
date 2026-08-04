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

function Read-DotEnvValue {
  param([string]$Path, [string]$Key)
  if (-not (Test-Path $Path)) { return $null }
  foreach ($line in Get-Content $Path) {
    $trim = $line.Trim()
    if (-not $trim -or $trim.StartsWith("#")) { continue }
    $parts = $trim -split "=", 2
    if ($parts.Count -ne 2) { continue }
    if ($parts[0].Trim() -eq $Key) {
      return $parts[1].Trim().Trim('"').Trim("'")
    }
  }
  return $null
}

$chatEnabled = $env:CHAT_MEMORY_ENABLED
if (-not $chatEnabled) { $chatEnabled = Read-DotEnvValue (Join-Path $Root "langgraph.env") "CHAT_MEMORY_ENABLED" }
if (-not $chatEnabled) { $chatEnabled = Read-DotEnvValue (Join-Path $Root ".env") "CHAT_MEMORY_ENABLED" }
$chatBase = $env:CHAT_MEMORY_BASE_URL
if (-not $chatBase) { $chatBase = Read-DotEnvValue (Join-Path $Root "langgraph.env") "CHAT_MEMORY_BASE_URL" }
if (-not $chatBase) { $chatBase = Read-DotEnvValue (Join-Path $Root ".env") "CHAT_MEMORY_BASE_URL" }
if (-not $chatBase) { $chatBase = "http://127.0.0.1:8420" }

if ($chatEnabled -and ($chatEnabled.ToLower() -eq "true" -or $chatEnabled -eq "1")) {
  $healthUrl = ($chatBase.TrimEnd("/") + "/health")
  try {
    $resp = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 2
    if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 300) {
      Write-Host "Chat memory sidecar OK: $healthUrl"
    } else {
      Write-Warning "CHAT_MEMORY_ENABLED=true but $healthUrl returned $($resp.StatusCode). Agent will degrade (no cross-turn chat memory)."
    }
  } catch {
    Write-Warning "CHAT_MEMORY_ENABLED=true but MemoryCore unreachable at $healthUrl. Start .\scripts\run_memory_core.ps1 — Agent still runs on three-store retrieval."
  }
}

$port = if ($env:LANGGRAPH_PORT) { $env:LANGGRAPH_PORT } else { "2025" }
Write-Host "Starting LangGraph on http://127.0.0.1:$port (graph id: agent)"
& .\.venv-langgraph\Scripts\langgraph.exe dev --port $port --no-browser
