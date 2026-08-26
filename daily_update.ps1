[CmdletBinding()]
param(
    [string]$PublicRepo = $PSScriptRoot,
    [string]$PrivateRepo = (Join-Path (Split-Path -Parent $PSScriptRoot) "LoL-SUP-Tracker-PrivateData"),
    [string]$PythonCommand = "python"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

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

function Assert-PrivateStagingContainsOnlyRaw {
    $stagedFiles = @(git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) {
        throw "PrivateDataのstage内容を確認できませんでした。"
    }

    $nonRawFiles = @($stagedFiles | Where-Object {
        $normalized = $_ -replace "\\", "/"
        -not $normalized.StartsWith("raw/", [System.StringComparison]::Ordinal)
    })
    if ($nonRawFiles.Count -ne 0) {
        throw "PrivateDataでraw以外がstageされています。commitせず停止します。"
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

    Push-Location $PrivateRepo
    try {
        Assert-CleanWorkingTree "PrivateData"
        Invoke-Checked git switch main
        Invoke-Checked git fetch origin
        Invoke-Checked git pull --ff-only origin main
        Assert-CleanWorkingTree "PrivateData"
    }
    finally {
        Pop-Location
    }

    Push-Location $PublicRepo
    try {
        Invoke-Checked $PythonCommand sync_private_data.py pull --apply
        Invoke-Checked $PythonCommand main.py
        Invoke-Checked $PythonCommand sync_private_data.py push
        Invoke-Checked $PythonCommand sync_private_data.py push --apply
    }
    finally {
        Pop-Location
    }

    $lolDate = (Get-Date).AddHours(-5).ToString("yyyy-MM-dd")

    Push-Location $PrivateRepo
    try {
        Invoke-Checked git add -- raw
        Assert-PrivateStagingContainsOnlyRaw
        Invoke-Checked git diff --cached --check

        git diff --cached --quiet
        $privateDiffExitCode = $LASTEXITCODE
        if ($privateDiffExitCode -eq 1) {
            Invoke-Checked git commit -m "Update LoL raw data $lolDate"
        }
        elseif ($privateDiffExitCode -eq 0) {
            Write-Host "PrivateData: コミットする変更はありません"
        }
        else {
            throw "PrivateDataの差分確認に失敗しました (exit $privateDiffExitCode)。"
        }

        # Publicを更新する前に、差分の有無を問わずPrivateDataのremote同期を確定する。
        Invoke-Checked git push origin main
    }
    finally {
        Pop-Location
    }

    Push-Location $PublicRepo
    try {
        Assert-PublicRawUntracked
        Invoke-Checked git add .
        Assert-PublicRawUntracked
        Invoke-Checked -Command git -CommandArguments @("-c", "core.whitespace=cr-at-eol", "diff", "--cached", "--check")

        git diff --cached --quiet
        $publicDiffExitCode = $LASTEXITCODE
        if ($publicDiffExitCode -eq 1) {
            Invoke-Checked git commit -m "Update LoL data $lolDate"
            Invoke-Checked git push origin build
        }
        elseif ($publicDiffExitCode -eq 0) {
            Write-Host "Public: コミットする変更はありません"
        }
        else {
            throw "Publicの差分確認に失敗しました (exit $publicDiffExitCode)。"
        }
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
