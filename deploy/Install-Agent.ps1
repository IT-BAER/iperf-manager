<#
.SYNOPSIS
    iperf-manager Agent Deployment Script for Windows Server.

.DESCRIPTION
    Installs iperf3, clones the iperf-manager repository, creates a config,
    registers a startup scheduled task, and opens firewall ports.
    Idempotent - safe to re-run.  Use -Uninstall to reverse everything.

.PARAMETER Token
    API key for agent authentication (optional).

.PARAMETER Port
    REST API listen port (default: 9001).

.PARAMETER IperfPorts
    Comma-separated iperf3 autostart ports (default: "5211,5212").

.PARAMETER InstallDir
    Installation directory (default: C:\iperf-manager).

.PARAMETER Uninstall
    Remove agent, scheduled task, config and firewall rules.

.EXAMPLE
    .\Install-Agent.ps1
    .\Install-Agent.ps1 -Token "mySecretKey" -Port 9001
    .\Install-Agent.ps1 -Uninstall
#>
[CmdletBinding()]
param(
    [string]$Token       = "",
    [int]$Port           = 9001,
    [string]$IperfPorts  = "5211,5212",
    [string]$InstallDir  = "C:\iperf-manager",
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

# ── Constants ────────────────────────────────────────────────────────
$TaskName       = "iperf-agent"
$TaskDescription = "iperf-manager Agent (headless) - network performance testing"
$ConfigDir      = Join-Path $InstallDir "config\iperf3-agent"
$LogDir         = Join-Path $InstallDir "logs"
$RepoUrl        = "https://github.com/IT-BAER/iperf-manager.git"
$RepoZipUrl     = "https://github.com/IT-BAER/iperf-manager/archive/refs/heads/main.zip"
$Iperf3Dir      = Join-Path $InstallDir "iperf3"
$FwRulePrefix   = "iperf-manager"
$Iperf3Release  = "https://api.github.com/repos/ar51an/iperf3-win-builds/releases/latest"
$PythonInstallerUrl = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
$GitInstallerUrl = "https://github.com/git-for-windows/git/releases/latest/download/Git-64-bit.exe"
$TokenGenerated = $false

# ── Helpers ──────────────────────────────────────────────────────────
function Write-Step  { param([string]$Msg) Write-Host "[INFO]  $Msg" -ForegroundColor Cyan }
function Write-Ok    { param([string]$Msg) Write-Host "[ OK ]  $Msg" -ForegroundColor Green }
function Write-Warn  { param([string]$Msg) Write-Host "[WARN]  $Msg" -ForegroundColor Yellow }
function Write-Err   { param([string]$Msg) Write-Host "[ERR ]  $Msg" -ForegroundColor Red }

function Refresh-Path {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"
}

function Resolve-Python {
    foreach ($candidate in @("python", "python3", "py -3")) {
        try {
            $verOutput = & cmd /c "$candidate --version 2>&1"
            if ($verOutput -match "Python (\d+)\.(\d+)") {
                $major = [int]$Matches[1]
                $minor = [int]$Matches[2]
                if ($major -ge 3 -and $minor -ge 9) {
                    if ($candidate -eq "py -3") {
                        $bin = "py -3"
                    } else {
                        $resolved = Get-Command $candidate -ErrorAction SilentlyContinue
                        if ($resolved) { $bin = $resolved.Source } else { $bin = $candidate }
                    }
                    return [pscustomobject]@{
                        Bin = $bin
                        Major = $major
                        Minor = $minor
                    }
                }
            }
        } catch { }
    }

    foreach ($path in @(
        "C:\\Program Files\\Python312\\python.exe",
        "C:\\Program Files\\Python311\\python.exe",
        "C:\\Program Files\\Python310\\python.exe",
        "C:\\Python312\\python.exe",
        "C:\\Python311\\python.exe",
        "C:\\Python310\\python.exe"
    )) {
        if (-not (Test-Path $path)) { continue }
        try {
            $verOutput = & $path --version 2>&1
            if ($verOutput -match "Python (\d+)\.(\d+)") {
                $major = [int]$Matches[1]
                $minor = [int]$Matches[2]
                if ($major -ge 3 -and $minor -ge 9) {
                    return [pscustomobject]@{
                        Bin = $path
                        Major = $major
                        Minor = $minor
                    }
                }
            }
        } catch { }
    }

    return $null
}

function Install-Python {
    Write-Step "Downloading Python installer ..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $installerPath = Join-Path $env:TEMP "python-installer-amd64.exe"
    Invoke-WebRequest -Uri $PythonInstallerUrl -OutFile $installerPath -UseBasicParsing

    Write-Step "Installing Python silently ..."
    Start-Process -FilePath $installerPath -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0" -Wait

    # Some Python installers return before path propagation; wait for the binary.
    $pythonCandidates = @(
        "C:\\Program Files\\Python312\\python.exe",
        "C:\\Program Files\\Python311\\python.exe",
        "C:\\Program Files\\Python310\\python.exe",
        "C:\\Python312\\python.exe",
        "C:\\Python311\\python.exe",
        "C:\\Python310\\python.exe"
    )
    $pythonReady = $false
    for ($i = 0; $i -lt 36; $i++) {
        if ($pythonCandidates | Where-Object { Test-Path $_ }) {
            $pythonReady = $true
            break
        }
        Start-Sleep -Seconds 5
    }

    Remove-Item -Path $installerPath -Force -ErrorAction SilentlyContinue
    Refresh-Path
    if (-not $pythonReady) {
        throw "Python installer finished but python.exe was not detected in common install paths"
    }
}

function Install-Git {
    Write-Step "Downloading Git for Windows installer ..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $installerPath = Join-Path $env:TEMP "git-installer-amd64.exe"
    Invoke-WebRequest -Uri $GitInstallerUrl -OutFile $installerPath -UseBasicParsing

    Write-Step "Installing Git silently ..."
    Start-Process -FilePath $installerPath -ArgumentList "/VERYSILENT /NORESTART /NOCANCEL /SP-" -Wait
    Remove-Item -Path $installerPath -Force -ErrorAction SilentlyContinue
    Refresh-Path

    # Ensure current session can find git immediately after install.
    foreach ($gitPath in @("C:\\Program Files\\Git\\cmd\\git.exe", "C:\\Program Files\\Git\\bin\\git.exe")) {
        if (Test-Path $gitPath) {
            $gitDir = Split-Path $gitPath -Parent
            if ($env:Path -notlike "*$gitDir*") {
                $env:Path = "$gitDir;$env:Path"
            }
            break
        }
    }
}

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]$identity
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# ── Admin check ──────────────────────────────────────────────────────
if (-not (Test-Admin)) {
    Write-Err "This script must be run as Administrator."
    Write-Host "Right-click PowerShell -> 'Run as Administrator', then try again."
    exit 1
}

# ═════════════════════════════════════════════════════════════════════
#  UNINSTALL
# ═════════════════════════════════════════════════════════════════════
if ($Uninstall) {
    Write-Host ""
    Write-Step "Uninstalling iperf-manager agent ..."

    # Stop running agent processes
    $agentProcs = Get-Process -Name "python*" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*main_agent.py*" }
    foreach ($proc in $agentProcs) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        Write-Ok "Stopped agent process (PID $($proc.Id))"
    }

    # Remove scheduled task
    $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existingTask) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Ok "Removed scheduled task '$TaskName'"
    }

    # Remove firewall rules
    Get-NetFirewallRule -DisplayName "${FwRulePrefix}*" -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule -ErrorAction SilentlyContinue
    Write-Ok "Removed firewall rules"

    # Remove install directory
    if (Test-Path $InstallDir) {
        Remove-Item -Path $InstallDir -Recurse -Force
        Write-Ok "Removed $InstallDir"
    }

    Write-Host ""
    Write-Ok "iperf-manager agent uninstalled successfully."
    exit 0
}

# ═════════════════════════════════════════════════════════════════════
#  INSTALL / UPDATE
# ═════════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "   iperf-manager Agent Installer (Windows)              " -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. Check Python 3.9+ ────────────────────────────────────────────
Write-Step "Checking Python ..."
$pythonInfo = Resolve-Python
if (-not $pythonInfo) {
    Write-Warn "Python 3.9+ not found. Attempting automatic installation ..."
    try {
        Install-Python
    } catch {
        Write-Err "Automatic Python install failed: $_"
    }
    $pythonInfo = Resolve-Python
}

if (-not $pythonInfo) {
    Write-Err "Python 3.9+ is required but not found."
    Write-Host ""
    Write-Host "Install Python from https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "  - Check 'Add python.exe to PATH' during installation" -ForegroundColor Yellow
    Write-Host "  - Restart this script after installing Python" -ForegroundColor Yellow
    exit 1
}

$PythonBin = $pythonInfo.Bin
$pyMajor = $pythonInfo.Major
$pyMinor = $pythonInfo.Minor
Write-Ok "Python found: $PythonBin ($pyMajor.$pyMinor)"

if (-not $Token) {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $rng.Dispose()
    $Token = -join ($bytes | ForEach-Object { $_.ToString('x2') })
    $TokenGenerated = $true
    Write-Ok "Generated API token automatically"
}

# ── 2. Install iperf3 ───────────────────────────────────────────────
Write-Step "Checking iperf3 ..."
$iperf3Exe = Join-Path $Iperf3Dir "iperf3.exe"
$iperf3InPath = Get-Command "iperf3" -ErrorAction SilentlyContinue

if (Test-Path $iperf3Exe) {
    Write-Ok "iperf3 already installed at $iperf3Exe"
} elseif ($iperf3InPath) {
    Write-Ok "iperf3 found in PATH: $($iperf3InPath.Source)"
    $iperf3Exe = $iperf3InPath.Source
} else {
    Write-Step "Downloading iperf3 for Windows ..."
    New-Item -ItemType Directory -Path $Iperf3Dir -Force | Out-Null

    try {
        # Fetch latest release info from ar51an/iperf3-win-builds
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $releaseInfo = Invoke-RestMethod -Uri $Iperf3Release -UseBasicParsing

        # Find the zip asset (prefer 64-bit)
        $asset = $releaseInfo.assets |
            Where-Object { $_.name -match "iperf3.*win.*64.*\.zip$" -or $_.name -match "iperf3.*\.zip$" } |
            Select-Object -First 1

        if (-not $asset) {
            # Fallback: grab any zip asset
            $asset = $releaseInfo.assets |
                Where-Object { $_.name -match "\.zip$" } |
                Select-Object -First 1
        }

        if (-not $asset) {
            throw "No zip asset found in latest release"
        }

        $zipPath = Join-Path $env:TEMP "iperf3-download.zip"
        $extractPath = Join-Path $env:TEMP "iperf3-extract"

        Write-Step "Downloading $($asset.name) ..."
        Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath -UseBasicParsing

        # Extract
        if (Test-Path $extractPath) { Remove-Item -Path $extractPath -Recurse -Force }
        Expand-Archive -Path $zipPath -DestinationPath $extractPath -Force

        # Copy iperf3.exe and any required DLLs (cygwin, msys2, etc.)
        $files = Get-ChildItem -Path $extractPath -Recurse -Include "iperf3.exe","iperf3*.dll","cygwin*.dll","msys*.dll","libiperf*.dll"
        foreach ($f in $files) {
            Copy-Item -Path $f.FullName -Destination $Iperf3Dir -Force
        }

        # Cleanup temp files
        Remove-Item -Path $zipPath -Force -ErrorAction SilentlyContinue
        Remove-Item -Path $extractPath -Recurse -Force -ErrorAction SilentlyContinue

        if (Test-Path $iperf3Exe) {
            Write-Ok "iperf3 installed to $Iperf3Dir"
        } else {
            throw "iperf3.exe not found after extraction"
        }
    } catch {
        Write-Err "Failed to download iperf3: $_"
        Write-Host ""
        Write-Host "Manual install:" -ForegroundColor Yellow
        Write-Host "  1. Download from https://github.com/ar51an/iperf3-win-builds/releases" -ForegroundColor Yellow
        Write-Host "  2. Extract iperf3.exe (and DLLs) to $Iperf3Dir" -ForegroundColor Yellow
        Write-Host "  3. Re-run this script" -ForegroundColor Yellow
        exit 1
    }
}

# ── 3. Clone or update repository ───────────────────────────────────
Write-Step "Setting up repository in $InstallDir ..."
$gitDir = Join-Path $InstallDir ".git"

$gitCmd = Get-Command "git" -ErrorAction SilentlyContinue
if (-not $gitCmd) {
    Write-Warn "Git not found. Attempting automatic installation ..."
    try {
        Install-Git
    } catch {
        Write-Err "Automatic Git install failed: $_"
    }
    $gitCmd = Get-Command "git" -ErrorAction SilentlyContinue
}

$canUseGit = $null -ne $gitCmd

if ($canUseGit -and (Test-Path $gitDir)) {
    Write-Step "Repository exists - pulling latest changes ..."
    & git -C $InstallDir fetch --quiet origin 2>$null
    $resetResult = & git -C $InstallDir reset --hard origin/main --quiet 2>&1
    if ($LASTEXITCODE -ne 0) {
        & git -C $InstallDir reset --hard origin/master --quiet 2>$null
    }
    Write-Ok "Repository updated"
} elseif ($canUseGit) {
    # Preserve iperf3 and config dirs if they already exist
    $preserveDirs = @($Iperf3Dir, $ConfigDir, $LogDir) | Where-Object { Test-Path $_ }
    $tempBackups = @{}
    foreach ($dir in $preserveDirs) {
        $backupPath = Join-Path $env:TEMP ("iperf-backup-" + (Split-Path $dir -Leaf))
        if (Test-Path $backupPath) { Remove-Item -Path $backupPath -Recurse -Force }
        Copy-Item -Path $dir -Destination $backupPath -Recurse -Force
        $tempBackups[$dir] = $backupPath
    }

    if (Test-Path $InstallDir) { Remove-Item -Path $InstallDir -Recurse -Force }
    & git clone --quiet $RepoUrl $InstallDir 2>$null
    Write-Ok "Repository cloned to $InstallDir"

    # Restore preserved directories
    foreach ($entry in $tempBackups.GetEnumerator()) {
        Copy-Item -Path $entry.Value -Destination $entry.Key -Recurse -Force
        Remove-Item -Path $entry.Value -Recurse -Force
    }
} else {
    Write-Warn "Git is unavailable. Falling back to repository ZIP download ..."

    # Preserve iperf3 and config dirs if they already exist
    $preserveDirs = @($Iperf3Dir, $ConfigDir, $LogDir) | Where-Object { Test-Path $_ }
    $tempBackups = @{}
    foreach ($dir in $preserveDirs) {
        $backupPath = Join-Path $env:TEMP ("iperf-backup-" + (Split-Path $dir -Leaf))
        if (Test-Path $backupPath) { Remove-Item -Path $backupPath -Recurse -Force }
        Copy-Item -Path $dir -Destination $backupPath -Recurse -Force
        $tempBackups[$dir] = $backupPath
    }

    $zipPath = Join-Path $env:TEMP "iperf-manager-main.zip"
    $extractPath = Join-Path $env:TEMP "iperf-manager-main-extract"
    if (Test-Path $zipPath) { Remove-Item -Path $zipPath -Force }
    if (Test-Path $extractPath) { Remove-Item -Path $extractPath -Recurse -Force }

    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $RepoZipUrl -OutFile $zipPath -UseBasicParsing
    Expand-Archive -Path $zipPath -DestinationPath $extractPath -Force

    $sourceDir = Get-ChildItem -Path $extractPath -Directory | Select-Object -First 1
    if (-not $sourceDir) {
        Write-Err "Repository archive extraction failed"
        exit 1
    }

    if (Test-Path $InstallDir) { Remove-Item -Path $InstallDir -Recurse -Force }
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    Copy-Item -Path (Join-Path $sourceDir.FullName "*") -Destination $InstallDir -Recurse -Force
    Write-Ok "Repository extracted to $InstallDir"

    foreach ($entry in $tempBackups.GetEnumerator()) {
        Copy-Item -Path $entry.Value -Destination $entry.Key -Recurse -Force
        Remove-Item -Path $entry.Value -Recurse -Force
    }

    Remove-Item -Path $zipPath -Force -ErrorAction SilentlyContinue
    Remove-Item -Path $extractPath -Recurse -Force -ErrorAction SilentlyContinue
}

# ── 4. Create configuration ─────────────────────────────────────────
Write-Step "Writing configuration ..."
New-Item -ItemType Directory -Path $ConfigDir -Force | Out-Null
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

$configFile = Join-Path $ConfigDir "config.json"
$configObj = @{
    autostart    = $IperfPorts
    bind_host    = "0.0.0.0"
    port         = $Port
    iperf3_path  = $iperf3Exe
    advertise_ip = ""
    api_token    = $Token
}
$configObj | ConvertTo-Json -Depth 4 | Set-Content -Path $configFile -Encoding UTF8
Write-Ok "Config written to $configFile"

# ── 5. Create scheduled task ────────────────────────────────────────
Write-Step "Creating scheduled task ..."

# Remove existing task if present (idempotent)
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    # Stop the running task first
    if ($existingTask.State -eq "Running") {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Build the python command
# Use the python executable resolved earlier; handle "py -3" specially
if ($PythonBin -eq "py -3") {
    $exePath  = "py"
    $argList  = "-3 `"$InstallDir\main_agent.py`""
} else {
    $exePath  = $PythonBin
    $argList  = "`"$InstallDir\main_agent.py`""
}

# Build environment variables string for the action
# We set LOCALAPPDATA to redirect config, and AGENT_LOGDIR for logs
$envVars = "LOCALAPPDATA=$($InstallDir)\config"
if ($Token) { $envVars += ";AGENT_API_KEY=$Token" }

$action = New-ScheduledTaskAction `
    -Execute $exePath `
    -Argument $argList `
    -WorkingDirectory $InstallDir

$trigger = New-ScheduledTaskTrigger -AtStartup

$principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 9999)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description $TaskDescription `
    -Force | Out-Null

# Set environment variables system-wide so the task picks them up
# Config directory override: agent reads from $LOCALAPPDATA/iperf3-agent/config.json
[Environment]::SetEnvironmentVariable("LOCALAPPDATA_IPERF", "$InstallDir\config", "Machine")
[Environment]::SetEnvironmentVariable("AGENT_LOGDIR", $LogDir, "Machine")
if ($Token) {
    [Environment]::SetEnvironmentVariable("AGENT_API_KEY", $Token, "Machine")
}

# Create a wrapper script that sets env vars and launches the agent
$wrapperScript = Join-Path $InstallDir "start-agent.cmd"
$wrapperContent = @"
@echo off
REM iperf-manager agent launcher - sets environment and starts the agent
set "LOCALAPPDATA=$InstallDir\config"
set "AGENT_LOGDIR=$LogDir"
"@
if ($Token) {
    $wrapperContent += "`nset `"AGENT_API_KEY=$Token`""
}
$wrapperContent += @"

cd /d "$InstallDir"
"$exePath" $argList
"@
Set-Content -Path $wrapperScript -Value $wrapperContent -Encoding ASCII

# Re-register task using the wrapper to ensure env vars are set
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$wrapperScript`"" `
    -WorkingDirectory $InstallDir

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description $TaskDescription `
    -Force | Out-Null

Write-Ok "Scheduled task '$TaskName' created (runs at startup as SYSTEM)"

# ── 6. Firewall rules ───────────────────────────────────────────────
Write-Step "Configuring firewall rules ..."

# Remove old rules first (idempotent)
Get-NetFirewallRule -DisplayName "${FwRulePrefix}*" -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule -ErrorAction SilentlyContinue

# API port
New-NetFirewallRule `
    -DisplayName "${FwRulePrefix} API (TCP ${Port})" `
    -Direction Inbound -Protocol TCP -LocalPort $Port `
    -Action Allow -Profile Any | Out-Null

# Discovery port
New-NetFirewallRule `
    -DisplayName "${FwRulePrefix} Discovery (UDP 9999)" `
    -Direction Inbound -Protocol UDP -LocalPort 9999 `
    -Action Allow -Profile Any | Out-Null

# iperf3 ports (TCP + UDP)
$portList = $IperfPorts -split "," | ForEach-Object { $_.Trim() }
foreach ($p in $portList) {
    New-NetFirewallRule `
        -DisplayName "${FwRulePrefix} iperf3 (TCP ${p})" `
        -Direction Inbound -Protocol TCP -LocalPort ([int]$p) `
        -Action Allow -Profile Any | Out-Null
    New-NetFirewallRule `
        -DisplayName "${FwRulePrefix} iperf3 (UDP ${p})" `
        -Direction Inbound -Protocol UDP -LocalPort ([int]$p) `
        -Action Allow -Profile Any | Out-Null
}
Write-Ok "Firewall rules created"

# ── 7. Start the agent ──────────────────────────────────────────────
Write-Step "Starting agent ..."
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 3

$taskState = (Get-ScheduledTask -TaskName $TaskName).State
if ($taskState -eq "Running") {
    Write-Ok "Agent is running"
} else {
    Write-Warn "Task state: $taskState (may take a moment to start)"
}

# ── 8. Summary ───────────────────────────────────────────────────────
Write-Host ""
Write-Host "========================================================" -ForegroundColor Green
Write-Host "   Installation Complete                                " -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Install directory : $InstallDir" -ForegroundColor Cyan
Write-Host "  Config file       : $configFile" -ForegroundColor Cyan
Write-Host "  Log directory     : $LogDir" -ForegroundColor Cyan
Write-Host "  iperf3 binary     : $iperf3Exe" -ForegroundColor Cyan
Write-Host "  Scheduled task    : $TaskName" -ForegroundColor Cyan
Write-Host "  API port          : ${Port}/tcp" -ForegroundColor Cyan
Write-Host "  Discovery port    : 9999/udp" -ForegroundColor Cyan
Write-Host "  iperf3 ports      : $IperfPorts" -ForegroundColor Cyan
if ($TokenGenerated) {
    Write-Host "  API token         : $Token" -ForegroundColor Yellow
    Write-Host "  Token source      : generated automatically" -ForegroundColor Yellow
} else {
    Write-Host "  API token         : (provided)" -ForegroundColor Cyan
}
Write-Host ""
if ($TokenGenerated) {
    Write-Warn "Save this token now. Use it when manually adding the agent in the dashboard so the server can refresh and control the agent securely."
    Write-Host ""
}
Write-Host "  Verify with:" -ForegroundColor Yellow
Write-Host "    curl http://localhost:${Port}/status" -ForegroundColor White
Write-Host "    Invoke-RestMethod http://localhost:${Port}/status" -ForegroundColor White
Write-Host ""
