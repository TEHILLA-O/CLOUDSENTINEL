# Starts the four local processes in separate windows. Tokens are the documented development values.
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  Write-Error "Create the virtualenv first. See the README."
  exit 1
}
New-Item -ItemType Directory -Force -Path (Join-Path $root "data") | Out-Null

function Start-ServiceWindow($title, $command) {
  Start-Process powershell -ArgumentList "-NoExit", "-Command", $command
}

$common = "`$env:FAULT_TOKEN='dev-fault-token'; `$env:FAULT_INJECTION_ENABLED='true'; Set-Location '$root'"
Start-ServiceWindow "analysis-azure" "$common; `$env:ENVIRONMENT_NAME='azure-dev'; `$env:ENVIRONMENT_PROVIDER='azure'; & '$python' -m uvicorn analysis_api.main:app --port 8001"
Start-ServiceWindow "analysis-gcp" "$common; `$env:ENVIRONMENT_NAME='gcp-dev'; `$env:ENVIRONMENT_PROVIDER='gcp'; & '$python' -m uvicorn analysis_api.main:app --port 8002"
Start-ServiceWindow "control-plane" @"
`$env:ADMIN_TOKEN='dev-admin-token'; `$env:READER_TOKEN='dev-reader-token'; `$env:GATEWAY_TOKEN='dev-gateway-token'; `$env:FAULT_TOKEN='dev-fault-token'; `$env:ANALYSIS_AZURE_URL='http://127.0.0.1:8001'; `$env:ANALYSIS_GCP_URL='http://127.0.0.1:8002'; `$env:DATABASE_URL='sqlite+aiosqlite:///./data/control-plane.db'; Set-Location '$root'; & '$python' -m uvicorn cloudsentinel_control.main:app --port 8000
"@
Start-ServiceWindow "gateway" "`$env:CONTROL_PLANE_URL='http://127.0.0.1:8000'; `$env:GATEWAY_TOKEN='dev-gateway-token'; Set-Location '$root'; & '$python' -m uvicorn cloudsentinel_gateway.main:app --port 8081"
