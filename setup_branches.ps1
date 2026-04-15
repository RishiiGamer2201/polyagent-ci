<#
.SYNOPSIS
    PolyAgent CI — Branch Setup Script (PowerShell)
    Creates git worktrees for each task in the manifest.

.DESCRIPTION
    Reads a task manifest JSON file and creates isolated git worktrees
    for each agent task, all branching from the same base commit on main.

.PARAMETER ManifestPath
    Path to the manifest JSON file.

.EXAMPLE
    .\setup_branches.ps1 -ManifestPath "manifests\manifest_20250115_103000_gemini.json"
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$ManifestPath,

    [Parameter(Mandatory=$false)]
    [string]$WorktreeDir = "worktrees",

    [Parameter(Mandatory=$false)]
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

# ─── Colors ───────────────────────────────────────────────
function Write-Info    { param($msg) Write-Host "ℹ️  $msg" -ForegroundColor Cyan }
function Write-Success { param($msg) Write-Host "✅ $msg" -ForegroundColor Green }
function Write-Warn    { param($msg) Write-Host "⚠️  $msg" -ForegroundColor Yellow }
function Write-Fail    { param($msg) Write-Host "❌ $msg" -ForegroundColor Red }

# ─── Validate ─────────────────────────────────────────────
if (-not (Test-Path $ManifestPath)) {
    Write-Fail "Manifest not found: $ManifestPath"
    exit 1
}

# Read manifest
Write-Info "Reading manifest from: $ManifestPath"
$manifestContent = Get-Content $ManifestPath -Raw | ConvertFrom-Json
$tasks = if ($manifestContent.tasks) { $manifestContent.tasks } else { $manifestContent }

Write-Info "Found $($tasks.Count) tasks in manifest"

# ─── Clean existing worktrees ─────────────────────────────
if ($Clean -and (Test-Path $WorktreeDir)) {
    Write-Warn "Cleaning existing worktrees..."
    foreach ($task in $tasks) {
        $branch = $task.branch
        $worktreePath = Join-Path $WorktreeDir ($branch -replace "/", "_")
        if (Test-Path $worktreePath) {
            Write-Info "  Removing worktree: $worktreePath"
            git worktree remove $worktreePath --force 2>$null
        }
        # Delete branch if exists
        git branch -D $branch 2>$null
    }
    if (Test-Path $WorktreeDir) {
        Remove-Item $WorktreeDir -Recurse -Force
    }
}

# ─── Get base commit ─────────────────────────────────────
$baseCommit = git rev-parse HEAD
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Failed to get HEAD commit. Are you in a git repo?"
    exit 1
}
Write-Info "Base commit: $($baseCommit.Substring(0, 8))..."

$baseBranch = git rev-parse --abbrev-ref HEAD
Write-Info "Base branch: $baseBranch"

# ─── Create worktree directory ────────────────────────────
if (-not (Test-Path $WorktreeDir)) {
    New-Item -ItemType Directory -Path $WorktreeDir | Out-Null
}

# ─── Create worktrees ────────────────────────────────────
$results = @()

foreach ($task in $tasks) {
    $taskId = $task.task_id
    $branch = $task.branch
    $agent = $task.agent
    $safeBranch = $branch -replace "/", "_"
    $worktreePath = Join-Path $WorktreeDir $safeBranch

    Write-Info "Creating worktree for task '$taskId' on branch '$branch'..."

    # Check if branch already exists
    $branchExists = git branch --list $branch
    if ($branchExists) {
        Write-Warn "  Branch '$branch' already exists, reusing..."
        git worktree add $worktreePath $branch 2>$null
    } else {
        # Create new branch from base commit
        git worktree add -b $branch $worktreePath $baseCommit
    }

    if ($LASTEXITCODE -eq 0) {
        Write-Success "  Worktree created: $worktreePath"

        # Copy shared contracts to worktree
        $sharedSrc = "shared"
        $sharedDst = Join-Path $worktreePath "shared"
        if (Test-Path $sharedSrc) {
            Copy-Item -Path $sharedSrc -Destination $sharedDst -Recurse -Force
            Write-Info "  Copied shared/ contracts to worktree"
        }

        $results += [PSCustomObject]@{
            TaskId    = $taskId
            Agent     = $agent
            Branch    = $branch
            Worktree  = $worktreePath
            Status    = "✅ Created"
        }
    } else {
        Write-Fail "  Failed to create worktree for '$taskId'"
        $results += [PSCustomObject]@{
            TaskId    = $taskId
            Agent     = $agent
            Branch    = $branch
            Worktree  = $worktreePath
            Status    = "❌ Failed"
        }
    }
}

# ─── Verify isolation ────────────────────────────────────
Write-Host ""
Write-Info "Verifying worktree isolation..."
$worktrees = git worktree list
Write-Host $worktrees

# ─── Summary ─────────────────────────────────────────────
Write-Host ""
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor White
Write-Host "  WORKTREE SETUP SUMMARY" -ForegroundColor White
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor White
Write-Host ""
$results | Format-Table -AutoSize
Write-Host ""
Write-Host "  Base commit: $($baseCommit.Substring(0, 8))" -ForegroundColor Gray
Write-Host "  Base branch: $baseBranch" -ForegroundColor Gray
Write-Host "  Total worktrees: $($results.Count)" -ForegroundColor Gray
Write-Host ""
Write-Success "Branch setup complete. Each agent has an isolated worktree."
