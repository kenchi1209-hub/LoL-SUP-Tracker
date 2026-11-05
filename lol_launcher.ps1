# LoL match-data launcher (PowerShell 5.1 compatible).
$PublicRoot = 'C:\Users\kissx\Desktop\LoL-Analytics'
$PrivateDataRoot = 'C:\Users\kissx\Desktop\LoL-SUP-Tracker-PrivateData'

function Convert-CodePoints {
    param([int[]]$CodePoints)

    return -join ($CodePoints | ForEach-Object { [char]$_ })
}

$LabelStart = Convert-CodePoints 0x8D77, 0x52D5
$LabelExit = Convert-CodePoints 0x7D42, 0x4E86
$LabelChoice = Convert-CodePoints 0x9078, 0x629E

function Wait-ForLauncherInput {
    Write-Host ''
    [void](Read-Host 'Press Enter to return to the menu')
}

function Invoke-Watcher {
    param(
        [switch]$Live
    )

    Set-Location -LiteralPath $PublicRoot

    if ($Live) {
        & python .\lcu_watcher.py --data-root $PrivateDataRoot --live --auto-publish
    }
    else {
        & python .\lcu_watcher.py --data-root $PrivateDataRoot
    }

    return $LASTEXITCODE
}

function Invoke-DailyUpdate {
    Set-Location -LiteralPath $PublicRoot
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\daily_update.ps1
    return $LASTEXITCODE
}

try {
    $shouldExit = $false
    while (-not $shouldExit) {
        Clear-Host
        Write-Host 'LoL Launcher'
        Write-Host ("[1] Ranked Watcher {0}" -f $LabelStart)
        Write-Host '[2] Daily Update'
        Write-Host '[3] Watcher dry-run'
        Write-Host ("[0] {0}" -f $LabelExit)

        $selection = Read-Host ("{0} [1]" -f $LabelChoice)
        if ([string]::IsNullOrWhiteSpace($selection)) {
            $selection = '1'
        }

        switch ($selection.Trim()) {
            '1' {
                Write-Host 'Starting Ranked Watcher. Press Ctrl+C to stop it.'
                $exitCode = Invoke-Watcher -Live
                if ($exitCode -ne 0) {
                    Write-Host "Watcher exited with code $exitCode." -ForegroundColor Red
                }
                Wait-ForLauncherInput
            }
            '2' {
                Write-Host 'Running Daily Update.'
                $exitCode = Invoke-DailyUpdate
                if ($exitCode -ne 0) {
                    Write-Host "Daily Update exited with code $exitCode." -ForegroundColor Red
                }
                Wait-ForLauncherInput
            }
            '3' {
                Write-Host 'Starting Watcher dry-run.'
                $exitCode = Invoke-Watcher
                if ($exitCode -ne 0) {
                    Write-Host "Watcher dry-run exited with code $exitCode." -ForegroundColor Red
                }
                Wait-ForLauncherInput
            }
            '0' {
                Write-Host 'Exiting.'
                $shouldExit = $true
            }
            default {
                Write-Host 'Invalid selection. Enter 0, 1, 2, or 3.' -ForegroundColor Yellow
                Wait-ForLauncherInput
            }
        }
    }
}
catch [System.Management.Automation.PipelineStoppedException] {
    # Exit quietly when Ctrl+C stops the launcher.
    Write-Host ''
    Write-Host 'Launcher stopped.'
}
