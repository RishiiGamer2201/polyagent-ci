<#
.SYNOPSIS
    PolyAgent CI - Branch Setup Script (PowerShell)
    Creates git worktrees for each task in the manifest.

.PARAMETER ManifestPath
    Path to the manifest JSON file.

.EXAMPLE
    .\setup_branches.ps1 -ManifestPath "manifests\manifest_offline.json"
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$ManifestPath,

    [Parameter(Mandatory=$false)]
    [string]$WorktreeDir = "worktrees",

    [Parameter(Mandatory=$false)]
    [switch]$Clean
)

$ErrorActionPreference = "Continue"

function Write-Info    { param($msg) Write-Host "[INFO]  $msg" -ForegroundColor Cyan }
function Write-Success { param($msg) Write-Host "[OK]    $msg" -ForegroundColor Green }
function Write-Warn    { param($msg) Write-Host "[WARN]  $msg" -ForegroundColor Yellow }
function Write-Fail    { param($msg) Write-Host "[ERROR] $msg" -ForegroundColor Red }

# Validate manifest exists
if (-not (Test-Path $ManifestPath)) {
    Write-Fail "Manifest not found: $ManifestPath"
    exit 1
}

# Read manifest
Write-Info "Reading manifest from: $ManifestPath"
$manifestContent = Get-Content $ManifestPath -Raw | ConvertFrom-Json
$tasks = if ($manifestContent.tasks) { $manifestContent.tasks } else { $manifestContent }

Write-Info "Found $($tasks.Count) tasks in manifest"

# Clean existing worktrees if requested
if ($Clean -and (Test-Path $WorktreeDir)) {
    Write-Warn "Cleaning existing worktrees..."
    foreach ($task in $tasks) {
        $branch = $task.branch
        $safeBranch = $branch -replace "/", "_"
        $worktreePath = Join-Path $WorktreeDir $safeBranch
        if (Test-Path $worktreePath) {
            Write-Info "  Removing worktree: $worktreePath"
            git worktree remove $worktreePath --force 2>$null
        }
        git branch -D $branch 2>$null
    }
}

# Get base commit
$baseCommit = git rev-parse HEAD 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Failed to get HEAD commit. Are you in a git repo?"
    exit 1
}
$baseBranch = git rev-parse --abbrev-ref HEAD 2>$null
Write-Info "Base commit : $($baseCommit.Substring(0,8))..."
Write-Info "Base branch : $baseBranch"

# Create worktree root directory
if (-not (Test-Path $WorktreeDir)) {
    New-Item -ItemType Directory -Path $WorktreeDir | Out-Null
    Write-Info "Created directory: $WorktreeDir"
}

# Create a worktree per task
$results = @()

foreach ($task in $tasks) {
    $taskId    = $task.task_id
    $branch    = $task.branch
    $agent     = $task.agent
    $safeBranch = $branch -replace "/", "_"
    $worktreePath = Join-Path $WorktreeDir $safeBranch

    Write-Info "Creating worktree [$taskId] on branch [$branch]..."

    $branchExists  = git branch --list $branch
    $worktreeExists = Test-Path $worktreePath

    if ($worktreeExists) {
        Write-Warn "  Worktree already exists, reusing: $worktreePath"
        $exitCode = 0
    } elseif ($branchExists) {
        Write-Warn "  Branch '$branch' exists, adding worktree..."
        $null = git worktree add $worktreePath $branch 2>&1
        $exitCode = $LASTEXITCODE
    } else {
        $null = git worktree add -b $branch $worktreePath $baseCommit 2>&1
        $exitCode = $LASTEXITCODE
    }

    if ($exitCode -eq 0) {
        # Copy shared contracts into worktree
        $sharedSrc = Join-Path (Get-Location) "shared"
        $sharedDst = Join-Path $worktreePath "shared"
        if (Test-Path $sharedSrc) {
            Copy-Item -Path $sharedSrc -Destination $sharedDst -Recurse -Force
            Write-Info "  Copied shared/ contracts"
        }

        Write-Success "Worktree ready: $worktreePath"
        $results += [PSCustomObject]@{
            TaskId   = $taskId
            Agent    = $agent
            Branch   = $branch
            Worktree = $worktreePath
            Status   = "Created"
        }
    } else {
        Write-Fail "Failed to create worktree for '$taskId'"
        $results += [PSCustomObject]@{
            TaskId   = $taskId
            Agent    = $agent
            Branch   = $branch
            Worktree = $worktreePath
            Status   = "FAILED"
        }
    }
}

# Verify isolation
Write-Host ""
Write-Info "Verifying worktree isolation..."
git worktree list

# Summary table
Write-Host ""
Write-Host "======================================================" -ForegroundColor White
Write-Host "  WORKTREE SETUP SUMMARY" -ForegroundColor White
Write-Host "======================================================" -ForegroundColor White
$results | Format-Table -AutoSize
Write-Host "  Base commit : $($baseCommit.Substring(0,8))" -ForegroundColor Gray
Write-Host "  Total       : $($results.Count) worktrees" -ForegroundColor Gray
Write-Host ""
Write-Success "Branch setup complete. Each agent has an isolated worktree."
