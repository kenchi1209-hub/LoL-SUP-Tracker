# No LoL or Watcher process is started by these tests.
. "$PSScriptRoot\start_lol_with_watcher.ps1" -DryRun

function Assert-Equal($actual, $expected, $label) {
    if ($actual -ne $expected) { throw "$label : expected $expected, got $actual" }
}

$script:processNames = @()
$script:lockfileExists = $false
function Get-Process {
    param([string[]]$Name, $ErrorAction)
    foreach ($item in $Name) {
        if ($script:processNames -contains $item) { [pscustomobject]@{ Name = $item } }
    }
}
function Test-Path {
    param($LiteralPath, $PathType)
    return $script:lockfileExists
}

$script:processNames = @('RiotClientServices')
Assert-Equal (Test-LeagueClientRunning) $false 'Riot Client alone'
Assert-Equal (Test-LeagueClientReady) $false 'No UX and no lockfile'
$script:processNames = @('LeagueClient')
Assert-Equal (Test-LeagueClientRunning) $true 'LeagueClient running'
Assert-Equal (Test-LeagueClientReady) $false 'LeagueClient alone is not ready'
$script:processNames = @('LeagueClientUx')
Assert-Equal (Test-LeagueClientRunning) $true 'LeagueClientUx running'
Assert-Equal (Test-LeagueClientReady) $false 'UX without lockfile is not ready'
$script:lockfileExists = $true
Assert-Equal (Test-LeagueClientReady) $true 'UX and lockfile ready'
$script:processNames = @()
Assert-Equal (Test-LeagueClientReady) $false 'Lockfile without UX is not ready'

function Get-CimInstance {
    param($ClassName, $ErrorAction)
    @(
        [pscustomobject]@{ CommandLine = 'python lcu_watcher.py --live --auto-publish' },
        [pscustomobject]@{ CommandLine = 'python lcu_watcher.py --live' },
        [pscustomobject]@{ CommandLine = 'python another.py --live --auto-publish' },
        [pscustomobject]@{ CommandLine = 'python lcu_watcher.py --auto-publish' }
    )
}
Assert-Equal (@(Get-RunningRankedWatcher).Count) 1 'Watcher requires all three arguments'
Write-Host 'Launcher process and readiness tests passed.'
