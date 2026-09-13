# Mobile access for the Firebase frontend (https://fo-droid.web.app).
# Problem: frontend built with NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 only works
# on this PC (on a phone, 127.0.0.1 = the phone, so the app falls back to
# offline/cached data). Fix: expose the local backend via a public HTTPS
# Cloudflare quick-tunnel URL, rebuild the static export with that URL, and
# redeploy to Firebase Hosting.
#
# Usage: double-click Start-Mobile-Tunnel.cmd (or run this script).
# Keep BOTH this window and the backend window open while using your mobile.
# NOTE: quick-tunnel URLs are random and change on every restart -- re-run this
# script after a reboot/tunnel restart (it rebuilds + redeploys automatically).

$ErrorActionPreference = "Stop"

$BackendHealth = "http://127.0.0.1:8000/health/live"
$ProjectRoot = $PSScriptRoot
$FrontendDir = Join-Path $ProjectRoot "frontend"
$LogDir = Join-Path ([IO.Path]::GetTempPath()) "droid-mobile-tunnel"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$LogOut = Join-Path $LogDir "cf-out.log"
$LogErr = Join-Path $LogDir "cf-err.log"

# 1. Backend must already be running (Start-Backend.cmd).
Write-Host "Checking backend at http://127.0.0.1:8000 ..."
try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri $BackendHealth -TimeoutSec 5
    if ($r.StatusCode -ne 200) { throw "status $($r.StatusCode)" }
    Write-Host "  Backend is UP." -ForegroundColor Green
} catch {
    Write-Host "" 
    Write-Host "  Backend is NOT reachable at http://127.0.0.1:8000." -ForegroundColor Red
    Write-Host "  Start it first with Start-Backend.cmd, wait for READY, then re-run this script."
    exit 1
}

# 2. Locate cloudflared.
$cf = (Get-Command cloudflared -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
if (-not $cf) {
    $cf = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
}
if (-not (Test-Path -LiteralPath $cf)) {
    Write-Host "  cloudflared.exe not found. Install from https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/" -ForegroundColor Red
    exit 1
}
Write-Host "  Using cloudflared: $cf"

# 3. Reuse an existing tunnel if one is already running, else start a new one.
$tunnelUrl = $null
$existing = Get-Process cloudflared -ErrorAction SilentlyContinue | Select-Object -First 1
foreach ($candidate in @($LogErr, "C:\Users\amarj\AppData\Local\Temp\opencode\cf-err.log")) {
    if ((Test-Path -LiteralPath $candidate)) {
        $m = Select-String -Path $candidate -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -AllMatches -ErrorAction SilentlyContinue | Select-Object -Last 1
        if ($m) { $tunnelUrl = $m.Matches[0].Value }
    }
    if ($tunnelUrl -and $existing) { break }
}
if ($tunnelUrl -and $existing) {
    # Quick tunnels die permanently on network blips ("Tunnel not found") while
    # the process keeps running -- probe before trusting a reused URL.
    Write-Host "  Found running tunnel, probing $tunnelUrl ..."
    $reuseOk = $false
    try {
        $reuseProbe = Invoke-WebRequest -UseBasicParsing -Uri "$tunnelUrl/health/live" -TimeoutSec 15
        if ($reuseProbe.StatusCode -eq 200) { $reuseOk = $true }
    } catch { $reuseOk = $false }
    if (-not $reuseOk) {
        Write-Host "  Old tunnel is dead (quick tunnels expire) -- killing it and starting fresh." -ForegroundColor Yellow
        Stop-Process -Id $existing.Id -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        $existing = $null
        $tunnelUrl = $null
    } else {
        Write-Host "  Reusing running tunnel: $tunnelUrl" -ForegroundColor Cyan
    }
}
if ($tunnelUrl -and $existing) {
    $tunnelProc = $existing
} else {
    Remove-Item -LiteralPath $LogOut -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $LogErr -ErrorAction SilentlyContinue
    Write-Host "  Starting new quick tunnel (this takes ~10s) ..."
    $tunnelProc = Start-Process -FilePath $cf -ArgumentList "tunnel", "--url", "http://127.0.0.1:8000" -RedirectStandardOutput $LogOut -RedirectStandardError $LogErr -WindowStyle Hidden -PassThru
    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 2
        if (Test-Path -LiteralPath $LogErr) {
            $m = Select-String -Path $LogErr -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -AllMatches -ErrorAction SilentlyContinue | Select-Object -Last 1
            if ($m) { $tunnelUrl = $m.Matches[0].Value; break }
        }
        if ($tunnelProc.HasExited) {
            Write-Host "  cloudflared exited early. Last log lines:" -ForegroundColor Red
            Get-Content $LogErr -ErrorAction SilentlyContinue | Select-Object -Last 15
            exit 1
        }
    }
    if (-not $tunnelUrl) {
        Write-Host "  Timed out waiting for tunnel URL. Last log lines:" -ForegroundColor Red
        Get-Content $LogErr -ErrorAction SilentlyContinue | Select-Object -Last 15
        exit 1
    }
    Write-Host "  Tunnel URL: $tunnelUrl" -ForegroundColor Cyan
}

# 4. Sanity-check the tunnel reaches the backend.
Write-Host "  Probing backend through tunnel ..."
try {
    $probe = Invoke-WebRequest -UseBasicParsing -Uri "$tunnelUrl/health/live" -TimeoutSec 20
    if ($probe.StatusCode -ne 200) { throw "status $($probe.StatusCode)" }
    Write-Host "  Tunnel probe OK." -ForegroundColor Green
} catch {
    Write-Host "  Tunnel probe failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "  The tunnel may still be warming up -- continuing with build anyway."
}

# 5. Rebuild frontend with the tunnel URL baked in (NEXT_PUBLIC_* is build-time).
Write-Host "  Building frontend with NEXT_PUBLIC_API_URL=$tunnelUrl ..."
Set-Location -LiteralPath $FrontendDir
if (-not (Test-Path -LiteralPath (Join-Path $FrontendDir "node_modules"))) {
    Write-Host "  node_modules missing - running npm install first..."
    npm install
    if ($LASTEXITCODE -ne 0) { exit 1 }
}
$env:NEXT_PUBLIC_API_URL = $tunnelUrl
npm run build
if ($LASTEXITCODE -ne 0) { exit 1 }

# 6. Deploy to Firebase Hosting.
Write-Host "  Deploying to Firebase Hosting (fo-droid) ..."
Set-Location -LiteralPath $ProjectRoot
firebase deploy --only hosting --project fo-droid --non-interactive
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host ""
Write-Host "  MOBILE READY" -ForegroundColor Green
Write-Host "  Site   : https://fo-droid.web.app (open on your mobile)"
Write-Host "  Backend: $tunnelUrl (tunnel to this PC)"
Write-Host ""
Write-Host "  Keep THIS window + the backend window open. If you close them,"
Write-Host "  or reboot, your mobile goes back to offline data until you re-run"
Write-Host "  Start-Mobile-Tunnel.cmd (new tunnel URL = automatic rebuild)."
Write-Host "  NOTE: broker login (FYERS) still callbacks to 127.0.0.1, so do the"
Write-Host "  broker OAuth on this PC; viewing live data works on mobile."
Wait-Process -Id $tunnelProc.Id
