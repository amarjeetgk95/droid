# Build the static frontend and deploy it to Firebase Hosting (project fo-droid).
# Run via Deploy-Frontend.cmd (double-click). There is no localhost frontend
# anymore: the live site is https://fo-droid.web.app and it calls the local
# backend at http://127.0.0.1:8000 (same machine, so loopback works).
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Join-Path $PSScriptRoot "frontend")

if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot "frontend\node_modules"))) {
    Write-Host "node_modules missing - running npm install first..."
    npm install
    if ($LASTEXITCODE -ne 0) { exit 1 }
}

# NEXT_PUBLIC_* vars are baked into the static export at build time.
$env:NEXT_PUBLIC_API_URL = "http://127.0.0.1:8000"
npm run build
if ($LASTEXITCODE -ne 0) { exit 1 }

Set-Location -LiteralPath $PSScriptRoot
firebase deploy --only hosting --project fo-droid --non-interactive
