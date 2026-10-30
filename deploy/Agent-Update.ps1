<#
.SYNOPSIS
    iperf-manager Agent updater (Windows).

.DESCRIPTION
    Run by the scheduled task "iperf-agent-update" when the dashboard asks an
    agent to update. Installs the latest GitHub release with that release's own
    Install-Agent.ps1. Manual use as Administrator: -Ref <tag> installs that tag
    even if it is not newer.
#>
[CmdletBinding()]
param(
    [string]$InstallDir = "C:\iperf-manager",
    [string]$Ref = ""
)

$ErrorActionPreference = "Stop"
$RepoReleaseApi = "https://api.github.com/repos/IT-BAER/iperf-manager/releases/latest"
$TaskName  = "iperf-agent"
# Outside the install dir: the installer's ZIP path deletes and recreates it.
$WorkDir   = Join-Path $env:ProgramData "iperf-manager"
$LogFile   = Join-Path $WorkDir "agent-update.log"
$StateFile = Join-Path $InstallDir "config\iperf3-agent\update-state.json"

function Write-Log { param([string]$Msg) Add-Content -LiteralPath $LogFile -Value "$(Get-Date -Format s) $Msg" }

$script:Installed = ""
$script:Target = ""
$script:Started = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()

function Write-State {
    param([string]$State, [string]$ErrorText = "")
    $data = [ordered]@{ state = $State; from = $script:Installed; to = $script:Target; started = $script:Started }
    if ($State -notin @("requested", "running")) { $data.finished = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() }
    if ($ErrorText) { $data.error = $ErrorText }
    $tmp = "$StateFile.tmp"
    [System.IO.File]::WriteAllText($tmp, ($data | ConvertTo-Json -Compress), (New-Object System.Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $tmp -Destination $StateFile -Force
}

New-Item -ItemType Directory -Path $WorkDir -Force | Out-Null
Set-Location $WorkDir
Write-Log "=== agent update start"

try {
    $constants = Get-Content -Raw -LiteralPath (Join-Path $InstallDir "core\constants.py")
    if ($constants -notmatch "AGENT_VERSION = '([0-9.]+)'") { throw "installed version not found" }
    $script:Installed = $Matches[1]

    if ($Ref) {
        if ($Ref -notmatch '^[A-Za-z0-9._/-]+$') { throw "invalid ref: $Ref" }
        $script:Target = $Ref
    } else {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $tag = [string](Invoke-RestMethod -Uri $RepoReleaseApi -UseBasicParsing -TimeoutSec 30).tag_name
        if ($tag -notmatch '^v\d+\.\d+\.\d+$') { throw "unexpected release tag: '$tag'" }
        $script:Target = $tag
        if ([version]$tag.Substring(1) -le [version]$script:Installed) {
            Write-Log "installed $($script:Installed) is current (latest $tag)"
            Write-State "current"
            exit 0
        }
    }

    Write-Log "updating $($script:Installed) -> $($script:Target)"
    Write-State "running"

    $zipPath = Join-Path $WorkDir "update.zip"
    $srcDir = Join-Path $WorkDir "update-src"
    if (Test-Path $srcDir) { Remove-Item -LiteralPath $srcDir -Recurse -Force }
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $zipUrl = "https://github.com/IT-BAER/iperf-manager/archive/refs/tags/$($script:Target).zip"
    try {
        Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing
    } catch {
        Invoke-WebRequest -Uri "https://github.com/IT-BAER/iperf-manager/archive/refs/heads/$($script:Target).zip" `
            -OutFile $zipPath -UseBasicParsing
    }
    Expand-Archive -Path $zipPath -DestinationPath $srcDir -Force
    $installer = Get-ChildItem -Path $srcDir -Recurse -Filter "Install-Agent.ps1" | Select-Object -First 1
    if (-not $installer) { throw "Install-Agent.ps1 not found in release archive" }

    # The release's own installer runs as a child so its 'exit' cannot end this script.
    $env:IPERF_MANAGER_REF = $script:Target
    $env:IPERF_AGENT_UPDATER = "1"
    # Windows PowerShell turns redirected native stderr into terminating errors under "Stop".
    $ErrorActionPreference = "Continue"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer.FullName -InstallDir $InstallDir *>> $LogFile
    $installerExit = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($installerExit -ne 0) { throw "installer exit code $installerExit" }

    Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $srcDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-State "ok"
    Write-Log "=== agent update done ($($script:Target))"
} catch {
    Write-Log "update failed: $_"
    # No file rollback: the ZIP path has already replaced the install dir. Try to bring the agent back.
    Start-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    try {
        # /status shows this text to dashboard users; the exception text can hold local paths.
        Write-State "failed" "update failed, see agent-update.log"
    } catch {
        Write-Log "state write failed: $_"
    }
    exit 1
}
