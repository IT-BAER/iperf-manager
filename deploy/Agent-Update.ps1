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

# All log writes go through Add-Content -Encoding UTF8: Windows PowerShell's *>> would append UTF-16.
function Write-Log { param([string]$Msg) Add-Content -LiteralPath $LogFile -Value "$(Get-Date -Format s) $Msg" -Encoding UTF8 }

$script:Installed = ""
$script:Target = ""
$script:BackedUp = $false
$script:TaskXml = ""
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

$RollbackDir = Join-Path $WorkDir "rollback"

function Remove-Tree {
    param([string]$Path)
    # rmdir does not follow junctions; Remove-Item -Recurse in Windows PowerShell does.
    # "Continue": Windows PowerShell turns redirected native stderr into terminating errors under "Stop".
    $ErrorActionPreference = "Continue"
    & cmd.exe /c rmdir /s /q "$Path" 2>$null
}

function Invoke-Mirror {
    param([string]$From, [string]$To)
    $ErrorActionPreference = "Continue"
    # /XJ: never follow junctions. Robocopy exit codes 0-7 mean success.
    & robocopy.exe $From $To /MIR /XJ /R:1 /W:1 /NP /NFL /NDL *>&1 | Add-Content -LiteralPath $LogFile -Encoding UTF8
    if ($LASTEXITCODE -ge 8) { throw "robocopy $From -> $To failed (exit code $LASTEXITCODE)" }
}

function Stop-Agent {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ExecutablePath -like "$InstallDir*" -or $_.CommandLine -like "*main_agent.py*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

function Restore-InstallDir {
    # Restores files only; a scheduled task the failed installer changed stays changed.
    Stop-Agent
    Remove-Tree -Path $InstallDir
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    # A folder recreated under C:\ inherits create rights for all users; code here runs as SYSTEM.
    $acl = New-Object System.Security.AccessControl.DirectorySecurity
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($sidValue in @("S-1-5-18", "S-1-5-32-544")) {
        $acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule(
            (New-Object System.Security.Principal.SecurityIdentifier($sidValue)), "FullControl",
            "ContainerInherit, ObjectInherit", "None", "Allow")))
    }
    Set-Acl -LiteralPath $InstallDir -AclObject $acl
    Invoke-Mirror -From $RollbackDir -To $InstallDir
    # The failed installer may have re-registered the task for the new code.
    if ($script:TaskXml) { Register-ScheduledTask -TaskName $TaskName -Xml $script:TaskXml -Force | Out-Null }
    Start-ScheduledTask -TaskName $TaskName
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
        Write-Warning ("Installing $Ref even if it is older than the installed version. Installers before v1.3.0 " +
            "reset the API firewall rule to any address and store the agent API key where all local users can read it.")
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

    Write-Log "backing up $InstallDir"
    Invoke-Mirror -From $InstallDir -To $RollbackDir
    $script:TaskXml = Export-ScheduledTask -TaskName $TaskName
    $script:BackedUp = $true

    # The release's own installer runs as a child so its 'exit' cannot end this script.
    $env:IPERF_MANAGER_REF = $script:Target
    $env:IPERF_AGENT_UPDATER = "1"
    # Windows PowerShell turns redirected native stderr into terminating errors under "Stop".
    $ErrorActionPreference = "Continue"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer.FullName -InstallDir $InstallDir *>&1 |
        Add-Content -LiteralPath $LogFile -Encoding UTF8
    $installerExit = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($installerExit -ne 0) { throw "installer exit code $installerExit" }

    Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $srcDir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Tree -Path $RollbackDir
    Write-State "ok"
    Write-Log "=== agent update done ($($script:Target))"
} catch {
    Write-Log "update failed: $_"
    # /status shows this text to dashboard users; the exception text can hold local paths.
    $errorText = "update failed, see agent-update.log"
    if ($script:BackedUp) {
        try {
            Restore-InstallDir
            Remove-Tree -Path $RollbackDir
            Write-Log "rolled back to $($script:Installed)"
            $errorText = "update failed and was rolled back, see agent-update.log"
        } catch {
            Write-Log "rollback failed: $_ (backup kept in $RollbackDir)"
            $errorText = "update failed, rollback failed, see agent-update.log"
        }
    }
    Start-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    try {
        Write-State "failed" $errorText
    } catch {
        Write-Log "state write failed: $_"
    }
    exit 1
}
