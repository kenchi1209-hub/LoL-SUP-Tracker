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

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$CommandArguments
    )

    & $Command @CommandArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed ($LASTEXITCODE): $Command $($CommandArguments -join ' ')"
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
        Invoke-Checked $PythonCommand main.py --data-root $PrivateRepo
        Invoke-Checked $PythonCommand verify_fight_raw_completeness.py --data-root $PrivateRepo
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
            throw "PrivateDataのraw/csv/excelに削除があります。commitせず停止します。"
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
            Invoke-Checked git commit -m "Update LoL data $lolDate"
            Invoke-Checked git push origin main
        }
        elseif ($privateDiffExitCode -eq 0) {
            Write-Host "PrivateData: コミットする変更はありません"
        }
        else {
            throw "PrivateDataの差分確認に失敗しました (exit $privateDiffExitCode)。"
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
    exit 0
}
catch {
    Write-Error $_
    exit 1
}
