[CmdletBinding()]
param(
    [string]$PublicRepo,
    [string]$PrivateRepo,
    [string]$PythonCommand = "python"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptPath = $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($scriptPath)) {
    throw "daily_update.ps1の実行パスを解決できません。powershell.exe -Fileで実行してください。"
}

$scriptDirectory = Split-Path -Parent $scriptPath
if ([string]::IsNullOrWhiteSpace($PublicRepo)) {
    $PublicRepo = $scriptDirectory
}
if ([string]::IsNullOrWhiteSpace($PrivateRepo)) {
    $PrivateRepo = Join-Path (Split-Path -Parent $scriptDirectory) "LoL-SUP-Tracker-PrivateData"
}

# Log only predefined facts through the helper; never redirect or persist the
# native process streams, which may contain credentials or account identifiers.
$script:AuditHelper = Join-Path $scriptDirectory 'daily_update_observability.py'
$script:AuditLog = $null
$script:DataStatus = 'UNKNOWN'
$script:FightStatus = 'UNKNOWN'
$script:PushStatus = 'SKIPPED'
$script:PrivateSha = 'UNKNOWN'
$script:PagesTrigger = 'SKIPPED'
$script:PagesRunId = ''
$script:PrivateUnchanged = $false
$script:PagesStatus = 'UNKNOWN'
$script:PagesDetail = 'PUSH_NOT_SUCCESS'
$script:ActiveStage = ''
$script:StartedAt = [DateTimeOffset]::UtcNow
$script:ExitCode = 1

function Write-Audit {
    param([string]$Event, [string]$State, [string]$Value = '')
    if (-not $script:AuditLog) { return }
    try {
        $arguments = @($script:AuditHelper, 'append', '--log-file', $script:AuditLog, '--event', $Event, '--state', $State)
        if ($Value) { $arguments += @('--value', $Value) }
        & $PythonCommand @arguments 2>$null
        if ($LASTEXITCODE -ne 0) { Write-Warning 'Daily Update log write failed; raw output was not saved.' }
    }
    catch { Write-Warning 'Daily Update log write failed; raw output was not saved.' }
}

try {
    $auditDir = Join-Path $PublicRepo 'logs\daily_update'
    $created = & $PythonCommand $script:AuditHelper init --directory $auditDir 2>$null
    if ($LASTEXITCODE -eq 0 -and $created) { $script:AuditLog = [string]$created }
    else { Write-Warning 'Daily Update log creation failed; raw output will not be saved.' }
}
catch { Write-Warning 'Daily Update log creation failed; raw output will not be saved.' }

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$CommandArguments
    )

    # Windows PowerShell can wrap native stderr as a non-terminating error.
    # It must not turn a successful native exit into a failure.
    $commandInfo = Get-Command -Name $Command -ErrorAction Stop | Select-Object -First 1
    $previousPreference = $ErrorActionPreference
    try {
        if ($commandInfo.CommandType -eq 'Application') { $ErrorActionPreference = 'Continue' }
        & $Command @CommandArguments
        $nativeExitCode = $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $previousPreference }
    if ($script:ActiveStage -in @('DATA_UPDATE', 'FIGHT_VALIDATION', 'COMMIT', 'PUSH')) {
        Write-Audit $script:ActiveStage $(if ($nativeExitCode -eq 0) { 'SUCCESS' } else { 'FAILED' }) ([string]$nativeExitCode)
    }
    if ($nativeExitCode -ne 0) {
        throw "Command failed ($nativeExitCode): $Command $($CommandArguments -join ' ')"
    }
}

function Assert-CleanWorkingTree {
    param([Parameter(Mandatory = $true)][string]$RepositoryName)

    $status = @(git status --porcelain=v1)
    if ($LASTEXITCODE -ne 0) {
        throw "$RepositoryName のgit statusに失敗しました。"
    }
    if ($status.Count -ne 0) {
        throw "$RepositoryName のworking treeがcleanではありません。変更を保持したまま停止します。"
    }
}

function Assert-PublicRawUntracked {
    $trackedRaw = @(git ls-files -- data/raw)
    if ($LASTEXITCODE -ne 0) {
        throw "Publicのdata/raw追跡状態を確認できませんでした。"
    }
    if ($trackedRaw.Count -ne 0) {
        throw "Publicのdata/raw配下にGit管理対象があるため停止します。"
    }
}

function Assert-PrivateStagingContainsOnlyData {
    $stagedFiles = @(git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) {
        throw "PrivateDataのstage内容を確認できませんでした。"
    }

    $unexpectedFiles = @($stagedFiles | Where-Object {
        $normalized = $_ -replace "\\", "/"
        -not (
            $normalized.StartsWith("raw/", [System.StringComparison]::Ordinal) -or
            $normalized.StartsWith("csv/", [System.StringComparison]::Ordinal) -or
            $normalized.StartsWith("excel/", [System.StringComparison]::Ordinal)
        )
    })
    if ($unexpectedFiles.Count -ne 0) {
        throw "PrivateDataでraw/csv/excel以外がstageされています。commitせず停止します。"
    }
}

function Assert-NoTrackedRawChanges {
    git diff --quiet -- raw
    if ($LASTEXITCODE -eq 1) {
        throw "既存PrivateData rawに変更または削除があります。commitせず停止します。"
    }
    if ($LASTEXITCODE -ne 0) {
        throw "PrivateData rawの差分確認に失敗しました。"
    }
}

try {
    if (-not (Test-Path -LiteralPath $PublicRepo -PathType Container)) {
        throw "Public repositoryが見つかりません: $PublicRepo"
    }
    if (-not (Test-Path -LiteralPath $PrivateRepo -PathType Container)) {
        throw "PrivateData repositoryが見つかりません: $PrivateRepo"
    }

    Push-Location $PublicRepo
    try {
        Assert-CleanWorkingTree "Public"
        Invoke-Checked git switch build
        Invoke-Checked git fetch origin
        Invoke-Checked git pull --ff-only origin build
        Assert-CleanWorkingTree "Public"
        Assert-PublicRawUntracked
    }
    finally {
        Pop-Location
    }

    $privateBaseSha = $null
    Push-Location $PrivateRepo
    try {
        Assert-CleanWorkingTree "PrivateData"
        Invoke-Checked git switch main
        Invoke-Checked git fetch origin
        Invoke-Checked git pull --ff-only origin main
        Assert-CleanWorkingTree "PrivateData"
        $privateBaseSha = (git rev-parse HEAD).Trim()
        if ($LASTEXITCODE -ne 0) {
            throw "PrivateDataの開始SHAを取得できませんでした。"
        }
    }
    finally {
        Pop-Location
    }

    Push-Location $PublicRepo
    try {
        $script:ActiveStage = 'DATA_UPDATE'
        Write-Audit 'DATA_UPDATE' 'STARTED'
        Invoke-Checked $PythonCommand main.py --data-root $PrivateRepo
        $script:DataStatus = 'SUCCESS'
        Write-Audit 'DATA_UPDATE' 'SUCCESS'
        $script:ActiveStage = 'FIGHT_VALIDATION'
        Write-Audit 'FIGHT_VALIDATION' 'STARTED'
        Invoke-Checked $PythonCommand verify_fight_raw_completeness.py --data-root $PrivateRepo
        $script:FightStatus = 'SUCCESS'
        Write-Audit 'FIGHT_VALIDATION' 'SUCCESS'
        $script:ActiveStage = ''
        Assert-CleanWorkingTree "Public"
    }
    finally {
        Pop-Location
    }

    $lolDate = (Get-Date).AddHours(-5).ToString("yyyy-MM-dd")

    Push-Location $PrivateRepo
    try {
        Assert-NoTrackedRawChanges

        $deletedFiles = @(git diff --name-only --diff-filter=D -- raw csv excel)
        if ($LASTEXITCODE -ne 0) {
            throw "PrivateDataの削除確認に失敗しました。"
        }
        if ($deletedFiles.Count -ne 0) {
            # Only obsolete, fully validated weekly Fight shards may disappear.
            $validator = Join-Path $PublicRepo 'fight_detail_shards.py'
            Invoke-Checked -Command $PythonCommand -CommandArguments (@($validator, '--validate-root', $PrivateRepo, '--deleted') + $deletedFiles)
        }

        $outsideData = @(git status --porcelain=v1 -- . ":(exclude)raw" ":(exclude)csv" ":(exclude)excel")
        if ($LASTEXITCODE -ne 0) {
            throw "PrivateDataの変更範囲を確認できませんでした。"
        }
        if ($outsideData.Count -ne 0) {
            throw "PrivateDataのraw/csv/excel以外に変更があります。commitせず停止します。"
        }

        Invoke-Checked git fetch origin main
        $remoteSha = (git rev-parse origin/main).Trim()
        if ($LASTEXITCODE -ne 0) {
            throw "PrivateData remote SHAを取得できませんでした。"
        }
        if ($remoteSha -ne $privateBaseSha) {
            throw "PrivateData mainが更新処理中に進んだため、pushせず停止します。"
        }

        Invoke-Checked git add -- raw csv excel
        Assert-PrivateStagingContainsOnlyData
        Invoke-Checked -Command git -CommandArguments @("-c", "core.whitespace=cr-at-eol", "diff", "--cached", "--check")

        git diff --cached --quiet
        $privateDiffExitCode = $LASTEXITCODE
        if ($privateDiffExitCode -eq 1) {
            $script:ActiveStage = 'COMMIT'
            Write-Audit 'COMMIT' 'STARTED'
            Invoke-Checked git commit -m "Update LoL data $lolDate"
            Write-Audit 'COMMIT' 'SUCCESS'
            $script:ActiveStage = 'PUSH'
            $script:PushStatus = 'FAILED'
            Write-Audit 'PUSH' 'STARTED'
            Invoke-Checked git push origin main
            $script:PushStatus = 'SUCCESS'
            Write-Audit 'PUSH' 'SUCCESS'
            $script:ActiveStage = ''
        }
        elseif ($privateDiffExitCode -eq 0) {
            # HEAD was confirmed equal to origin/main above; no commit was needed.
            $script:PrivateUnchanged = $true
            Write-Host "PrivateData: コミットする変更はありません"
            Write-Audit 'COMMIT' 'SKIPPED'
            Write-Audit 'PUSH' 'SKIPPED'
        }
        else {
            throw "PrivateDataの差分確認に失敗しました (exit $privateDiffExitCode)。"
        }
        $candidateSha = (git rev-parse HEAD 2>$null)
        if ($LASTEXITCODE -eq 0 -and $candidateSha -match '^[0-9a-fA-F]{40}$') {
            $script:PrivateSha = $candidateSha
            Write-Audit 'PRIVATE_SHA' 'SUCCESS' $candidateSha
        }
    }
    finally {
        Pop-Location
    }

    Push-Location $PublicRepo
    try {
        Assert-CleanWorkingTree "Public"
        Assert-PublicRawUntracked
    }
    finally {
        Pop-Location
    }

    Write-Host "LoLデータ更新が正常に完了しました。"
    $script:ExitCode = 0
}
catch {
    if ($script:ActiveStage -eq 'DATA_UPDATE') { $script:DataStatus = 'FAILED' }
    if ($script:ActiveStage -eq 'FIGHT_VALIDATION') { $script:FightStatus = 'FAILED' }
    if ($script:ActiveStage) { Write-Audit $script:ActiveStage 'FAILED' }
    Write-Host $_ -ForegroundColor Red
    $script:ExitCode = 1
}
finally {
    if ($script:DataStatus -eq 'SUCCESS' -and $script:FightStatus -eq 'SUCCESS' -and ($script:PushStatus -eq 'SUCCESS' -or $script:PrivateUnchanged) -and $script:PrivateSha -match '^[0-9a-fA-F]{40}$') {
        try {
            $pagesHelper = Join-Path $scriptDirectory 'daily_update_pages.py'
            $pagesArguments = @($pagesHelper, '--sha', $script:PrivateSha, '--data', $script:DataStatus, '--fight', $script:FightStatus, '--push', $script:PushStatus, '--lock-directory', (Join-Path $PublicRepo 'logs\daily_update'))
            if ($script:PrivateUnchanged) { $pagesArguments += '--unchanged' }
            $pagesJson = & $PythonCommand @pagesArguments 2>$null
            if ($LASTEXITCODE -ne 0) { throw 'Pages query unavailable' }
            $pages = $pagesJson | ConvertFrom-Json -ErrorAction Stop
            $states = @('SUCCESS', 'PENDING', 'FAILED', 'UNKNOWN')
            $reasons = @('DEPLOY_SUCCESS','DEPLOY_FAILED','RUN_PENDING','NO_MATCH','SHA_INVALID','API_FAILURE','API_TIMEOUT','METADATA_MISSING','MALFORMED_RESPONSE','EVIDENCE_MISMATCH','PUSH_NOT_SUCCESS','AUTH_FAILURE','DISPATCH_FAILED','RUN_NOT_FOUND','WAIT_TIMEOUT','CONDITIONS_NOT_MET')
            if ($pages.state -notin $states -or $pages.reason -notin $reasons) { throw 'Invalid Pages response' }
            if (($pages.state -eq 'SUCCESS' -and $pages.reason -ne 'DEPLOY_SUCCESS') -or
                ($pages.state -eq 'FAILED' -and $pages.reason -ne 'DEPLOY_FAILED') -or
                ($pages.state -eq 'PENDING' -and $pages.reason -notin @('RUN_PENDING','NO_MATCH','WAIT_TIMEOUT','RUN_NOT_FOUND')) -or
                ($pages.state -eq 'UNKNOWN' -and $pages.reason -in @('DEPLOY_SUCCESS','DEPLOY_FAILED','RUN_PENDING','NO_MATCH','WAIT_TIMEOUT','RUN_NOT_FOUND'))) { throw 'Inconsistent Pages response' }
            if ($pages.trigger -notin @('TRIGGERED','ALREADY_RUNNING','ALREADY_DEPLOYED','SKIPPED','UNKNOWN')) { throw 'Invalid trigger' }
            if ($null -ne $pages.run_id -and [string]$pages.run_id -notmatch '^\d{1,20}$') { throw 'Invalid run ID' }
            $script:PagesTrigger = $pages.trigger
            if ($null -ne $pages.run_id) { $script:PagesRunId = [string]$pages.run_id }
            $script:PagesStatus = $pages.state
            $script:PagesDetail = $pages.reason
        }
        catch { $script:PagesTrigger = 'UNKNOWN'; $script:PagesStatus = 'UNKNOWN'; $script:PagesDetail = 'API_FAILURE' }
    }
    $elapsedSeconds = [int][Math]::Floor(([DateTimeOffset]::UtcNow - $script:StartedAt).TotalSeconds)
    Write-Audit 'DATA_UPDATE' $script:DataStatus
    Write-Audit 'FIGHT_VALIDATION' $script:FightStatus
    Write-Audit 'PUSH' $script:PushStatus
    if ($script:PrivateSha -eq 'UNKNOWN') { Write-Audit 'PRIVATE_SHA' 'UNKNOWN' }
    Write-Audit 'PAGES_TRIGGER' $script:PagesTrigger
    if ($script:PagesRunId) { Write-Audit 'PAGES_RUN_ID' 'SUCCESS' $script:PagesRunId }
    Write-Audit 'PAGES' $script:PagesStatus $script:PagesDetail
    Write-Audit 'DURATION_SECONDS' 'SUCCESS' ([string]$elapsedSeconds)
    Write-Audit 'END' $(if ($script:ExitCode -eq 0) { 'SUCCESS' } else { 'FAILED' }) ([string]$script:ExitCode)
    Write-Host '========================================'
    Write-Host 'Daily Update Result'
    Write-Host "Data Update      : $script:DataStatus"
    Write-Host "Fight Validation : $script:FightStatus"
    Write-Host "PrivateData Push : $script:PushStatus"
    Write-Host "PrivateData SHA  : $script:PrivateSha"
    Write-Host "Pages Trigger    : $script:PagesTrigger"
    Write-Host "Pages Run ID     : $script:PagesRunId"
    Write-Host "Pages Deploy     : $script:PagesStatus"
    Write-Host "Pages Detail     : $script:PagesDetail"
    Write-Host "Duration         : $elapsedSeconds seconds"
    Write-Host "Log File         : $(if ($script:AuditLog) { $script:AuditLog } else { 'UNKNOWN' })"
    Write-Host '========================================'
}
exit $script:ExitCode
