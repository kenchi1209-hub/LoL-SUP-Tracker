[CmdletBinding()]
param([switch]$DryRun)

# Use the Riot-installed shortcut so its target, arguments and working directory
# stay the same as the user's normal League of Legends launch.
$PublicRoot = 'C:\Users\kissx\Desktop\LoL-Analytics'
$PrivateDataRoot = 'C:\Users\kissx\Desktop\LoL-SUP-Tracker-PrivateData'
$LeagueLockfile = 'C:\Riot Games\League of Legends\lockfile'
$ShortcutCandidates = @(
    'C:\Users\Public\Desktop\League of Legends.lnk',
    'C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Riot Games\League of Legends.lnk'
)

function Get-LeagueShortcut {
    $shell = New-Object -ComObject WScript.Shell
    foreach ($path in $ShortcutCandidates) {
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            $shortcut = $shell.CreateShortcut($path)
            if (-not $shortcut.TargetPath -or -not (Test-Path -LiteralPath $shortcut.TargetPath -PathType Leaf)) {
                throw "League shortcut target is unavailable: $path"
            }
            return [pscustomobject]@{
                Path = $path
                Target = $shortcut.TargetPath
                Arguments = $shortcut.Arguments
                WorkingDirectory = $shortcut.WorkingDirectory
            }
        }
    }
    throw 'League of Legends shortcut not found; refusing to guess launch arguments.'
}

function Get-RunningRankedWatcher {
    return @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
        $_.CommandLine -and
        $_.CommandLine -match '(?i)lcu_watcher\.py' -and
        $_.CommandLine -match '(?i)(?:^|\s)--live(?:\s|$)' -and
        $_.CommandLine -match '(?i)(?:^|\s)--auto-publish(?:\s|$)'
    })
}

function Test-LeagueClientRunning {
    return [bool](Get-Process -Name 'LeagueClient', 'LeagueClientUx' -ErrorAction SilentlyContinue)
}

function Test-LeagueClientReady {
    $ux = Get-Process -Name 'LeagueClientUx' -ErrorAction SilentlyContinue
    return [bool]($ux -and (Test-Path -LiteralPath $LeagueLockfile -PathType Leaf))
}

function Start-RankedWatcher {
    $watcherCommand = "Set-Location -LiteralPath '$PublicRoot'; & python .\lcu_watcher.py --data-root '$PrivateDataRoot' --live --auto-publish"
    $encodedCommand = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($watcherCommand))
    Start-Process -FilePath 'powershell.exe' -WorkingDirectory $PublicRoot `
        -ArgumentList @('-NoExit', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', $encodedCommand) -ErrorAction Stop
    Write-Host '[OK] Ranked Watcher started.' -ForegroundColor Green
}

try {
    Set-Location -LiteralPath $PublicRoot -ErrorAction Stop
    $shortcut = Get-LeagueShortcut
    $running = Test-LeagueClientRunning
    $ready = Test-LeagueClientReady

    if ($DryRun) {
        Write-Host "[DRY-RUN] Shortcut: $($shortcut.Path)"
        Write-Host "[DRY-RUN] Target: $($shortcut.Target)"
        Write-Host "[DRY-RUN] Arguments: $($shortcut.Arguments)"
        Write-Host "[DRY-RUN] WorkingDirectory: $($shortcut.WorkingDirectory)"
        Write-Host "[DRY-RUN] Launch: open shortcut $($shortcut.Path)"
        Write-Host "[DRY-RUN] LeagueClient or LeagueClientUx running: $running"
        Write-Host "[DRY-RUN] LCU ready (LeagueClientUx AND lockfile $LeagueLockfile): $ready"
        Write-Host "[DRY-RUN] Ranked Watcher already running: $(@(Get-RunningRankedWatcher).Count -gt 0)"
        Write-Host "[DRY-RUN] After LCU ready: python .\lcu_watcher.py --data-root `"$PrivateDataRoot`" --live --auto-publish"
        return
    }

    if ($running) {
        Write-Host '[INFO] League Client already running.'
    }
    else {
        Start-Process -FilePath $shortcut.Path -ErrorAction Stop
        Write-Host '[OK] League Client launch requested.'
    }

    $deadline = [DateTime]::UtcNow.AddSeconds(120)
    while (-not (Test-LeagueClientReady)) {
        if ([DateTime]::UtcNow -ge $deadline) {
            throw 'League Client did not become ready within 120 seconds; Watcher was not started.'
        }
        Write-Host '[INFO] Waiting for League Client (LeagueClientUx and lockfile)...'
        Start-Sleep -Seconds 3
    }

    Write-Host '[OK] League Client ready.'
    if (@(Get-RunningRankedWatcher).Count -gt 0) {
        Write-Host '[INFO] Ranked Watcher already running.'
    }
    else {
        Start-RankedWatcher
    }
}
catch [System.Management.Automation.PipelineStoppedException] {
    Write-Host 'Launcher stopped.'
}
catch {
    Write-Host ("[ERROR] {0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 1
}
