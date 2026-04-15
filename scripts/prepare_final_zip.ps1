param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d{2}$')]
    [string]$GroupNumber,

    [switch]$SkipZip
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$distRoot = Join-Path $repoRoot "dist"
$stageRoot = Join-Path $distRoot "final_delivery"
$submissionName = "Final_gp$GroupNumber"
$stageDir = Join-Path $stageRoot $submissionName
$zipPath = Join-Path $distRoot "$submissionName.zip"

$topLevelExcludedPatterns = @(
    ".git",
    ".venv",
    ".idea",
    ".vscode",
    ".claude",
    ".codex",
    ".codex_pytest_tmp",
    ".agents",
    ".cursor",
    "dist",
    "__pycache__",
    "pytest_tmp_*"
)

$excludedLeafPatterns = @(
    "__pycache__",
    ".pytest_cache",
    ".tmp_pytest",
    ".tmp_pytest_single",
    "pytest-cache-files-*"
)

$excludedRelativeDirectories = @(
    "model-test\cache",
    "model-test\outputs"
)

$excludedFilePatterns = @(
    "*.pyc",
    "*.pyo",
    "Thumbs.db",
    ".DS_Store",
    ".cursorrules",
    "AGENTS.md",
    "CLAUDE.md",
    "AI_CONTROL.md"
)

function Test-ExcludedDirectory {
    param(
        [string]$Path,
        [bool]$IsTopLevel = $false
    )

    $item = Get-Item -LiteralPath $Path -Force
    if ($IsTopLevel) {
        foreach ($pattern in $topLevelExcludedPatterns) {
            if ($item.Name -like $pattern) {
                return $true
            }
        }
    }

    foreach ($pattern in $excludedLeafPatterns) {
        if ($item.Name -like $pattern) {
            return $true
        }
    }

    $fullPath = [System.IO.Path]::GetFullPath($item.FullName)
    $rootPath = [System.IO.Path]::GetFullPath($repoRoot)
    if ($fullPath.StartsWith($rootPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        $relativePath = $fullPath.Substring($rootPath.Length).TrimStart([char[]]@(92, 47))
    }
    else {
        $relativePath = $item.Name
    }
    return $excludedRelativeDirectories -contains $relativePath
}

function Test-ExcludedFile {
    param([string]$Path)

    $item = Get-Item -LiteralPath $Path -Force
    foreach ($pattern in $excludedFilePatterns) {
        if ($item.Name -like $pattern) {
            return $true
        }
    }
    return $false
}

function Copy-RepositoryItem {
    param(
        [string]$SourcePath,
        [string]$DestinationPath,
        [bool]$IsTopLevel = $false
    )

    $item = Get-Item -LiteralPath $SourcePath -Force
    if ($item.PSIsContainer) {
        if (Test-ExcludedDirectory -Path $SourcePath -IsTopLevel:$IsTopLevel) {
            return
        }

        New-Item -ItemType Directory -Force -Path $DestinationPath | Out-Null
        foreach ($child in Get-ChildItem -LiteralPath $SourcePath -Force) {
            Copy-RepositoryItem -SourcePath $child.FullName -DestinationPath (Join-Path $DestinationPath $child.Name)
        }
        return
    }

    if (Test-ExcludedFile -Path $SourcePath) {
        return
    }

    $parent = Split-Path -Parent $DestinationPath
    if (-not [string]::IsNullOrWhiteSpace($parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    Copy-Item -LiteralPath $SourcePath -Destination $DestinationPath -Force
}

New-Item -ItemType Directory -Force -Path $distRoot | Out-Null
New-Item -ItemType Directory -Force -Path $stageRoot | Out-Null

if (Test-Path -LiteralPath $stageDir) {
    Remove-Item -LiteralPath $stageDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $stageDir | Out-Null

foreach ($item in Get-ChildItem -LiteralPath $repoRoot -Force) {
    Copy-RepositoryItem -SourcePath $item.FullName -DestinationPath (Join-Path $stageDir $item.Name) -IsTopLevel:$true
}

$requiredPaths = @(
    "app.py",
    "README.md",
    "requirements.txt",
    ".streamlit\config.toml",
    "reports\Final_Report.html"
)

foreach ($requiredPath in $requiredPaths) {
    $resolvedPath = Join-Path $stageDir $requiredPath
    if (-not (Test-Path -LiteralPath $resolvedPath)) {
        throw "Missing required delivery file: $requiredPath"
    }
}

if (-not $SkipZip) {
    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }
    Compress-Archive -Path $stageDir -DestinationPath $zipPath -Force
}

Write-Host "Prepared delivery folder: $stageDir"
if (-not $SkipZip) {
    Write-Host "Prepared zip file: $zipPath"
}
