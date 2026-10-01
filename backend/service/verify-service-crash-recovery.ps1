<#
  verify-service-crash-recovery.ps1
  ==================================
  End-to-end verification of the DROIDBackend Windows service.

  Proves, against the real machine:
    1. the service is installed and reaches RUNNING;
    2. the wrapper (droid-backend.exe) owns exactly ONE python.exe child;
    3. the API answers /health and /ready;
    4. exactly one PID listens on port 8000;
    5. /health/subsystems reports signal_worker = true;
    6. killing the python.exe child (simulated crash) is detected and the
       wrapper brings the backend back on its own;
    7. after recovery there is still exactly one wrapper, one python child,
       one listener and one boot in the log (no duplicated signal worker);
    8. (optional, -StopAfter) stopping the service leaves no orphan
       python.exe behind.

  Exit codes: 0 = every check passed, 1 = at least one check failed.
  Requires Administrator (killing a service child needs it). Run via
  verify-service.bat, which elevates itself.

  Usage:
    backend\service\verify-service.bat
    backend\service\verify-service.bat -StopAfter
    powershell -File backend\service\verify-service-crash-recovery.ps1 -BaseUrl http://127.0.0.1:8000
#>
[CmdletBinding()]
param(
    [string]$ServiceName = 'DROIDBackend',
    [string]$BaseUrl = 'http://127.0.0.1:8000',
    [int]$ReadyTimeoutSec = 180,
    [int]$RecoveryTimeoutSec = 240,
    [switch]$StopAfter
)

$ErrorActionPreference = 'Continue'
$script:Results = @()
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$LogDir = Join-Path $RepoRoot 'logs'
$AppLog = Join-Path $LogDir 'application.log'
$Report = Join-Path $LogDir 'verify-service-report.log'
$Port = 8000

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }

function Start-Report {
    try { Start-Transcript -Path $Report -Force -ErrorAction Stop | Out-Null }
    catch { Write-Host "  [warn] report transcript unavailable: $($_.Exception.Message)" -ForegroundColor Yellow }
}
function Stop-Report {
    try { Stop-Transcript -ErrorAction Stop | Out-Null } catch { }
}

function Write-Phase([string]$Text) {
    Write-Host ''
    Write-Host "== $Text" -ForegroundColor Cyan
}
function Add-Result([string]$Name, [bool]$Ok, [string]$Detail) {
    $script:Results += [pscustomobject]@{ Check = $Name; Ok = $Ok; Detail = $Detail }
    $tag = if ($Ok) { 'PASS' } else { 'FAIL' }
    $color = if ($Ok) { 'Green' } else { 'Red' }
    Write-Host ("  [{0}] {1} : {2}" -f $tag, $Name, $Detail) -ForegroundColor $color
}
function Abort([string]$Message) {
    Write-Host ''
    Write-Host "[ABORT] $Message" -ForegroundColor Red
    Write-Host ''
    Stop-Report
    exit 1
}
function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}
function Get-SvcState {
    $s = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($null -eq $s) { return 'NotInstalled' }
    return $s.Status.ToString()
}
function Invoke-Probe([string]$Url, [int]$TimeoutSec = 5) {
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
        return [pscustomobject]@{ Ok = $true; Status = [int]$r.StatusCode; Body = [string]$r.Content }
    } catch {
        $resp = $_.Exception.Response
        $status = 0
        if ($null -ne $resp) { $status = [int]$resp.StatusCode }
        return [pscustomobject]@{ Ok = $false; Status = $status; Body = '' }
    }
}
function Wait-Probe([string]$Url, [int]$TimeoutSec) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        $p = Invoke-Probe -Url $Url
        if ($p.Ok) {
            return [pscustomobject]@{ Ok = $true; Seconds = [math]::Round($sw.Elapsed.TotalSeconds, 1) }
        }
        Start-Sleep -Seconds 2
    }
    return [pscustomobject]@{ Ok = $false; Seconds = [math]::Round($sw.Elapsed.TotalSeconds, 1) }
}
function Get-WrapperProcesses {
    @(Get-CimInstance Win32_Process -Filter "Name='droid-backend.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ieq 'droid-backend.exe' })
}
function Get-PythonChildren([int]$ParentPid) {
    @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$ParentPid" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ieq 'python.exe' })
}
function Get-ListenPids([int]$LocalPort) {
    $pids = @()
    try {
        $pids = @(Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction Stop |
            Select-Object -ExpandProperty OwningProcess -Unique)
    } catch {
        $pids = @(netstat -ano | Select-String 'LISTENING' |
            ForEach-Object { $line = $_.Line.Trim() -replace '\s+', ' '; $f = $line.Split(' ')
                if ($f[1] -match (':' + $LocalPort + '$')) { $f[-1] } } |
            Select-Object -Unique)
    }
    @($pids)
}
function Read-LogSince([string]$Path, [long]$Offset) {
    if (-not (Test-Path $Path)) { return '' }
    $fs = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    try {
        if ($Offset -gt $fs.Length) { $Offset = 0 }
        $fs.Seek($Offset, [IO.SeekOrigin]::Begin) | Out-Null
        $sr = New-Object IO.StreamReader($fs)
        return $sr.ReadToEnd()
    } finally { $fs.Close() }
}
function Count-Matches([string]$Text, [string]$Marker) {
    if ([string]::IsNullOrEmpty($Text)) { return 0 }
    ([regex]::Matches($Text, [regex]::Escape($Marker))).Count
}

Start-Report

Write-Host '============================================================' -ForegroundColor White
Write-Host ' DROID Backend Service - crash-recovery verification' -ForegroundColor White
Write-Host '============================================================' -ForegroundColor White
Write-Host " Service : $ServiceName"
Write-Host " API     : $BaseUrl"
Write-Host " Logs    : $AppLog"
Write-Host " Report  : $Report"

# -- Phase 1: prerequisites --------------------------------------------------
Write-Phase 'Phase 1 - prerequisites'

$wrapper = Join-Path $PSScriptRoot 'droid-backend.exe'
$xml = Join-Path $PSScriptRoot 'droid-backend.xml'
if (-not (Test-Path $wrapper)) {
    Abort "Wrapper binary missing: $wrapper`n        Run download-winsw.bat first."
}
if (-not (Test-Path $xml)) {
    Abort "Service configuration missing: $xml"
}
Write-Host "  [ok] wrapper + config present"

$state = Get-SvcState
if ($state -eq 'NotInstalled') {
    Abort @"
Service "$ServiceName" is not installed - nothing to verify yet.

Install it first (one-time, Administrator):
    backend\service\install-service.bat
then start it:
    backend\service\start-service.bat
and re-run this verifier.
"@
}

if (-not (Test-Admin)) {
    Abort "Administrator rights are required (the verifier kills the service's own child process).`n        Use verify-service.bat, which self-elevates."
}

# -- Phase 2: bring the service up -------------------------------------------
Write-Phase 'Phase 2 - service state'
Write-Host "  SCM state: $state"

if ($state -ne 'Running') {
    Write-Host '  starting the service ...'
    & "$env:SystemRoot\System32\sc.exe" start $ServiceName | Out-Null
    $deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $deadline) {
        if ((Get-SvcState) -eq 'Running') { break }
        Start-Sleep -Seconds 2
    }
}
$state = Get-SvcState
Add-Result 'service RUNNING' ($state -eq 'Running') "SCM state = $state"
if ($state -ne 'Running') {
    Write-Host '  See logs\droid-backend.err.log (port 8000 conflict / bad .env).' -ForegroundColor Yellow
    Stop-Report
    exit 1
}

# -- Phase 3: baseline -------------------------------------------------------
Write-Phase 'Phase 3 - baseline (before the simulated crash)'

$wrappers = Get-WrapperProcesses
Add-Result 'one wrapper process' ($wrappers.Count -eq 1) ("droid-backend.exe count = " + $wrappers.Count)

$wrapperPid = 0
if ($wrappers.Count -ge 1) { $wrapperPid = [int]$wrappers[0].ProcessId }

$children = @()
if ($wrapperPid -gt 0) { $children = Get-PythonChildren -ParentPid $wrapperPid }
Add-Result 'one python child' ($children.Count -eq 1) ("python.exe children of pid $wrapperPid = " + $children.Count)
if ($children.Count -eq 0) {
    Abort "The wrapper has no python.exe child - the backend is not running.`n        Check logs\droid-backend.err.log."
}
$childPid = [int]$children[0].ProcessId
Write-Host "  wrapper pid = $wrapperPid, backend child pid = $childPid"

$live = Invoke-Probe -Url "$BaseUrl/health"
Add-Result '/health answers 200' ($live.Ok -and $live.Status -eq 200) "HTTP $($live.Status)"

Write-Host '  waiting for readiness (first boot can take ~1 minute: FYERS connect, DB restore) ...'
$ready = Wait-Probe -Url "$BaseUrl/ready" -TimeoutSec $ReadyTimeoutSec
Add-Result '/ready answers 200' $ready.Ok ("took $($ready.Seconds)s")

$listenPids = Get-ListenPids -LocalPort $Port
Add-Result 'one listener on port 8000' ($listenPids.Count -eq 1) ("PIDs listening = " + ($listenPids -join ','))

$sub = Invoke-Probe -Url "$BaseUrl/health/subsystems"
$signalOk = $false
$signalDetail = "HTTP $($sub.Status)"
if ($sub.Ok) {
    try {
        $obj = $sub.Body | ConvertFrom-Json
        $signalOk = [bool]$obj.signal_worker
        $signalDetail = "signal_worker = $($obj.signal_worker), central_feed = $($obj.central_feed), token_status = $($obj.token_status)"
    } catch { $signalDetail = 'subsystems JSON unreadable' }
}
Add-Result 'signal worker running' $signalOk $signalDetail

$logOffset = 0
if (Test-Path $AppLog) { $logOffset = (Get-Item $AppLog).Length }
Write-Host "  application.log offset before crash: $logOffset bytes"

# -- Phase 4: simulated crash ------------------------------------------------
Write-Phase 'Phase 4 - kill the Python child (simulated crash)'
$killSw = [Diagnostics.Stopwatch]::StartNew()
try {
    Stop-Process -Id $childPid -Force -ErrorAction Stop
} catch {
    Abort "Could not kill pid $childPid : $($_.Exception.Message)"
}
Add-Result 'python child killed' $true "Stop-Process -Force pid $childPid"
Start-Sleep -Seconds 2

$gone = -not (Get-Process -Id $childPid -ErrorAction SilentlyContinue)
Add-Result 'old child is gone' $gone "pid $childPid"
$alive = Get-SvcState
Add-Result 'wrapper survived (service still RUNNING)' ($alive -eq 'Running') "SCM state = $alive"

# -- Phase 5: automatic recovery --------------------------------------------
Write-Phase 'Phase 5 - automatic restart'
Write-Host '  WinSW restarts the child ~10 s after an unexpected exit; waiting for readiness ...'

$newChildPid = 0
$deadline = (Get-Date).AddSeconds($RecoveryTimeoutSec)
while ((Get-Date) -lt $deadline) {
    $kids = Get-PythonChildren -ParentPid $wrapperPid
    $fresh = @($kids | Where-Object { [int]$_.ProcessId -ne $childPid })
    if ($fresh.Count -ge 1) { $newChildPid = [int]$fresh[0].ProcessId; break }
    Start-Sleep -Seconds 1
}
$spawnSeconds = [math]::Round($killSw.Elapsed.TotalSeconds, 1)
Add-Result 'new python child appeared' ($newChildPid -gt 0) "new pid = $newChildPid after $($spawnSeconds)s"
if ($newChildPid -le 0) {
    Abort "No replacement child after $RecoveryTimeoutSec s. WinSW onfailure should fire after 10 s;`n        check logs\droid-backend.err.log and logs\droid-backend.out.log."
}

$recovered = Wait-Probe -Url "$BaseUrl/ready" -TimeoutSec $RecoveryTimeoutSec
$downtime = [math]::Round($killSw.Elapsed.TotalSeconds, 1)
Add-Result '/ready recovers' $recovered.Ok "ready again after $downtime s"

# -- Phase 6: exactly one of everything -------------------------------------
Write-Phase 'Phase 6 - no duplicates / no orphans'

$wrappers2 = Get-WrapperProcesses
Add-Result 'still one wrapper process' ($wrappers2.Count -eq 1) ("droid-backend.exe count = " + $wrappers2.Count)

$children2 = Get-PythonChildren -ParentPid $wrapperPid
Add-Result 'exactly one python child' ($children2.Count -eq 1) ("children = " + ($children2.ProcessId -join ','))

$orphans = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.ProcessId -eq $childPid })
Add-Result 'killed child not lingering' ($orphans.Count -eq 0) "old pid $childPid present = " + $orphans.Count

$listenPids2 = Get-ListenPids -LocalPort $Port
Add-Result 'exactly one listener on 8000' ($listenPids2.Count -eq 1) ("PIDs listening = " + ($listenPids2 -join ','))

$sub2 = Invoke-Probe -Url "$BaseUrl/health/subsystems"
$signalOk2 = $false
if ($sub2.Ok) {
    try { $signalOk2 = [bool]($sub2.Body | ConvertFrom-Json).signal_worker } catch { $signalOk2 = $false }
}
Add-Result 'signal worker running after restart' $signalOk2 "HTTP $($sub2.Status)"

# Log evidence for the recovery window (bytes appended since the kill).
$window = Read-LogSince -Path $AppLog -Offset $logOffset
$boots = Count-Matches -Text $window -Marker 'startup_single_instance_guard_ok'
$workerStart = Count-Matches -Text $window -Marker 'automated_signal_worker_started'
$posture = Count-Matches -Text $window -Marker 'startup_trading_safety_posture'
Add-Result 'exactly one boot in recovery window' ($boots -eq 1) "logs: startup_single_instance_guard_ok x$boots"
Add-Result 'trading posture logged on restart' ($posture -ge 1) "startup_trading_safety_posture x$posture"
Add-Result 'signal worker started once per boot' ($workerStart -ge 1) `
    "automated_signal_worker_started x$workerStart (2 lines per boot is normal: worker.py + main.py)"

if ($workerStart -gt 0 -and $boots -gt 0 -and $workerStart -gt (2 * $boots)) {
    Add-Result 'no duplicated signal worker' $false `
        "$workerStart start-lines for $boots boot(s) - more than one worker per process"
} else {
    Add-Result 'no duplicated signal worker' $true "consistent with $boots boot(s)"
}

# -- Phase 7: optional stop / orphan check ----------------------------------
$stopOk = $true
if ($StopAfter) {
    Write-Phase 'Phase 7 - stop the service and check for orphans'
    & "$env:SystemRoot\System32\sc.exe" stop $ServiceName | Out-Null
    $deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $deadline) {
        if ((Get-SvcState) -ne 'Running') { break }
        Start-Sleep -Seconds 2
    }
    $finalState = Get-SvcState
    Add-Result 'service stopped' ($finalState -eq 'Stopped') "SCM state = $finalState"

    $leftover = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { [int]$_.ParentProcessId -eq $wrapperPid })
    $stillWrapper = @(Get-WrapperProcesses).Count
    Add-Result 'no orphan python child' ($leftover.Count -eq 0) ("children left = " + $leftover.Count)
    Add-Result 'wrapper exited' ($stillWrapper -eq 0) "droid-backend.exe count = $stillWrapper"

    $shutdown = Read-LogSince -Path $AppLog -Offset $logOffset
    $stoppedMarker = Count-Matches -Text $shutdown -Marker 'SHUTDOWN COMPLETE'
    Add-Result 'graceful lifespan shutdown' ($stoppedMarker -ge 1) "SHUTDOWN COMPLETE x$stoppedMarker"
    $stopOk = ($finalState -eq 'Stopped') -and ($leftover.Count -eq 0)
}

# -- Summary -----------------------------------------------------------------
Write-Phase 'Summary'
$failed = @($script:Results | Where-Object { -not $_.Ok })
foreach ($r in $script:Results) {
    $tag = if ($r.Ok) { 'PASS' } else { 'FAIL' }
    $color = if ($r.Ok) { 'Green' } else { 'Red' }
    Write-Host ("  {0}  {1}" -f $tag, $r.Check) -ForegroundColor $color
}
Write-Host ''
Write-Host ("  killed pid {0} -> new pid {1}; ready again after {2}s" -f $childPid, $newChildPid, $downtime)
Write-Host ("  checks: {0} total, {1} failed" -f $script:Results.Count, $failed.Count)

if ($failed.Count -eq 0) {
    Write-Host ''
    Write-Host '  RESULT: PASS - the service supervises the backend and self-heals.' -ForegroundColor Green
    Write-Host '  Watch it live:  powershell Get-Content ' -NoNewline
    Write-Host $AppLog -NoNewline
    Write-Host ' -Wait -Tail 30'
    Write-Host ''
    Stop-Report
    exit 0
}

Write-Host ''
Write-Host '  RESULT: FAIL - see the failing checks above.' -ForegroundColor Red
Write-Host '  Next: logs\droid-backend.err.log, logs\droid-backend.out.log, docs\LOCAL_BACKEND_SERVICE.md' -ForegroundColor Yellow
Write-Host ''
Stop-Report
exit 1
