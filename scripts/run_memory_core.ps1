# Start TencentDB MemoryCore as Chat-memory sidecar for Claude Copilot (Windows)
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$defaultTencentRoot = "D:\GithubProject\TencentDB-Agent-Memory-feat-server_team\TencentDB-Agent-Memory-feat-server_team"
$TencentRoot = if ($env:TENCENTDB_MEMORY_ROOT) { $env:TENCENTDB_MEMORY_ROOT } else { $defaultTencentRoot }
$MemoryCore = Join-Path $TencentRoot "MemoryCore"
$GatewayConfig = Join-Path $Root "deploy\memory-core\tdai-gateway.standalone.yaml"
$DataDir = Join-Path $Root "data\chat_memory"

if (-not (Test-Path $MemoryCore)) {
  Write-Error @"
MemoryCore not found at: $MemoryCore
Set TENCENTDB_MEMORY_ROOT to the TencentDB-Agent-Memory repo root
(the folder that contains MemoryCore/).
"@
}

if (-not (Test-Path $GatewayConfig)) {
  Write-Error "Missing gateway config: $GatewayConfig"
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  Write-Error "Node.js is required (MemoryCore needs Node >= 22.16)."
}

$nodeVersion = (node -v) -replace "^v", ""
$major = [int]($nodeVersion.Split(".")[0])
if ($major -lt 22) {
  Write-Warning "Node $nodeVersion detected; MemoryCore recommends >= 22.16."
}

New-Item -ItemType Directory -Force -Path $DataDir | Out-Null

Push-Location $MemoryCore
try {
  if (-not (Test-Path ".\node_modules")) {
    Write-Host "Installing MemoryCore dependencies (npm install --ignore-scripts)..."
    # Windows: postinstall bash patch is optional; ignore-scripts avoids hard fail.
    npm install --ignore-scripts
  }
  if (-not (Test-Path ".\dist") -and -not (Test-Path ".\src\gateway\server.ts")) {
    Write-Host "Building MemoryCore..."
    npm run build
  }
} finally {
  Pop-Location
}

function Read-DotEnvValue {
  param(
    [string]$Path,
    [string]$Key
  )
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

$envFile = Join-Path $Root ".env"
$langgraphEnv = Join-Path $Root "langgraph.env"

$llmKey = $env:TDAI_LLM_API_KEY
if (-not $llmKey) { $llmKey = Read-DotEnvValue $envFile "LLM_MODEL_API_KEY" }
if (-not $llmKey) { $llmKey = Read-DotEnvValue $langgraphEnv "LLM_MODEL_API_KEY" }
if (-not $llmKey) { $llmKey = Read-DotEnvValue $envFile "BAI_LIAN_API_KEY" }
if (-not $llmKey) { $llmKey = Read-DotEnvValue $envFile "SILICON_KEY" }

$llmBase = $env:TDAI_LLM_BASE_URL
if (-not $llmBase) { $llmBase = Read-DotEnvValue $envFile "LLM_MODEL_BASE_URL" }
if (-not $llmBase) { $llmBase = Read-DotEnvValue $langgraphEnv "LLM_MODEL_BASE_URL" }
if (-not $llmBase) { $llmBase = "https://api.openai.com/v1" }

$llmModel = $env:TDAI_LLM_MODEL
if (-not $llmModel) { $llmModel = Read-DotEnvValue $envFile "LLM_MODEL_NAME" }
if (-not $llmModel) { $llmModel = Read-DotEnvValue $langgraphEnv "LLM_MODEL_NAME" }
if (-not $llmModel) { $llmModel = "gpt-4o-mini" }

$port = if ($env:TDAI_GATEWAY_PORT) { $env:TDAI_GATEWAY_PORT } else { "8420" }

$env:TDAI_GATEWAY_CONFIG = $GatewayConfig
$env:TDAI_GATEWAY_HOST = "127.0.0.1"
$env:TDAI_GATEWAY_PORT = "$port"
$env:TDAI_DATA_DIR = $DataDir
$env:TDAI_LLM_BASE_URL = $llmBase
$env:TDAI_LLM_MODEL = $llmModel
if ($llmKey) {
  $env:TDAI_LLM_API_KEY = $llmKey
} else {
  Write-Warning "No LLM API key found (TDAI_LLM_API_KEY / LLM_MODEL_API_KEY / BAI_LIAN_API_KEY / SILICON_KEY). Capture/extraction may be limited; /health should still work."
}

# Align with CHAT_MEMORY_API_KEY so /v2/* layer browse works when auth is enabled.
$gatewayKey = $env:TDAI_GATEWAY_API_KEY
if (-not $gatewayKey) { $gatewayKey = Read-DotEnvValue $envFile "CHAT_MEMORY_API_KEY" }
if (-not $gatewayKey) { $gatewayKey = Read-DotEnvValue $langgraphEnv "CHAT_MEMORY_API_KEY" }
if (-not $gatewayKey) { $gatewayKey = "claude-copilot-local-dev" }
$env:TDAI_GATEWAY_API_KEY = $gatewayKey
Write-Host "  apiKey : set (TDAI_GATEWAY_API_KEY / CHAT_MEMORY_API_KEY aligned)"

Write-Host "Starting MemoryCore Chat Memory sidecar"
Write-Host "  source : $MemoryCore"
Write-Host "  config : $GatewayConfig"
Write-Host "  data   : $DataDir"
Write-Host "  health : http://127.0.0.1:$port/health"
Write-Host "  note   : document KG remains Postgres/Qdrant/Neo4j — not this process"

Set-Location $MemoryCore
if (Test-Path ".\src\gateway\server.ts") {
  & node --import tsx src/gateway/server.ts
} elseif (Test-Path ".\dist\gateway\server.js") {
  & node dist/gateway/server.js
} else {
  Write-Error "Cannot find MemoryCore gateway entry (src/gateway/server.ts or dist/gateway/server.js)."
}
