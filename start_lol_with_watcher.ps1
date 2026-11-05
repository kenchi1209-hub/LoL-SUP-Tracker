[CmdletBinding()]
param(
    [switch]$DryRun
)

# PowerShell 5.1-compatible combined League Client and watcher launcher.
$PublicRoot = 'C:\Users\kissx\Desktop\LoL-Analytics'
$PrivateDataRoot = 'C:\Users\kissx\Desktop\LoL-SUP-Tracker-PrivateData'
$LeagueClientPath = 'C:\Riot Games\League of Legends\LeagueClient.exe'
$LeagueClientProcessName = 'LeagueClient'

function Convert-CodePoints {
    param([int[]]$CodePoints)

    return -join ($CodePoints | ForEach-Object { [char]$_ })
}

$TextStarted = Convert-CodePoints 0x3092, 0x8D77, 0x52D5, 0x3057, 0x307E, 0x3057, 0x305F
$TextWouldStart = Convert-CodePoints 0x3092, 0x8D77, 0x52D5, 0x3057, 0x307E, 0x3059
$TextAlreadyRunning = Convert-CodePoints 0x306F, 0x3059, 0x3067, 0x306B, 0x8D77, 0x52D5, 0x4E2D, 0x3067, 0x3059
$TextNotFound = Convert-CodePoints 0x304C, 0x898B, 0x3064, 0x304B, 0x308A, 0x307E, 0x305B, 0x3093

function Get-RunningRankedWatcher {
    return @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
        $_.CommandLine -and
        $_.CommandLine -match '(?i)lcu_watcher\.py' -and
        $_.CommandLine -match '(?i)(?:^|\s)--live(?:\s|$)' -and
        $_.CommandLine -match '(?i)(?:^|\s)--auto-publish(?:\s|$)'
    })
}

function Test-LeagueClientRunning {
    return [bool](Get-Process -Name $LeagueClientProcessName -ErrorAction SilentlyContinue)
}

function Start-RankedWatcher {
    $watcherCommand = "Set-Location -LiteralPath '$PublicRoot'; & python .\lcu_watcher.py --data-root '$PrivateDataRoot' --live --auto-publish"

    if ($DryRun) {
        Write-Host ("[DRY-RUN] Ranked Watcher {0}." -f $TextWouldStart)
        return
    }

    Start-Process -FilePath 'powershell.exe' `
        -WorkingDirectory $PublicRoot `
        -ArgumentList @('-NoExit', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', $watcherCommand)
    Write-Host ("[OK] Ranked Watcher {0}." -f $TextStarted) -ForegroundColor Green
}

function Start-LeagueClient {
    if (-not (Test-Path -LiteralPath $LeagueClientPath -PathType Leaf)) {
        Write-Host ("[ERROR] League Client {0}: {1}" -f $TextNotFound, $LeagueClientPath) -ForegroundColor Red
        return
    }

    if ($DryRun) {
        Write-Host ("[DRY-RUN] League Client {0}: {1}" -f $TextStarted, $LeagueClientPath)
        return
    }

    Start-Process -FilePath $LeagueClientPath
    Write-Host ("[OK] League Client {0}." -f $TextStarted) -ForegroundColor Green
}

try {
    Set-Location -LiteralPath $PublicRoot

    $watchers = Get-RunningRankedWatcher
    if ($watchers.Count -gt 0) {
        Write-Host ("[INFO] Ranked Watcher {0}." -f $TextAlreadyRunning) -ForegroundColor Cyan
    }
    else {
        Start-RankedWatcher
    }

    if (Test-LeagueClientRunning) {
        Write-Host ("[INFO] League Client {0}." -f $TextAlreadyRunning) -ForegroundColor Cyan
    }
    else {
        Start-LeagueClient
    }
}
catch [System.Management.Automation.PipelineStoppedException] {
    # Exit quietly when Ctrl+C stops this launcher.
    Write-Host ''
    Write-Host 'Launcher stopped.'
}
catch {
    Write-Host ("[ERROR] {0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 1
}
