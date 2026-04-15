"""
PolyAgent CI — Merge Coordinator

Merges agent branches in topological order (Backend → CRDT → Frontend → QA).
Runs test suite after each merge. On failure, runs git bisect and constructs
a fix prompt for the responsible agent.

Usage:
    python merge_coordinator.py --manifest manifests/manifest_*.json
    python merge_coordinator.py --manifest manifests/manifest_*.json --demo-mode
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from dag_orchestrator import DagOrchestrator

# ─── Constants ────────────────────────────────────────────

LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)
MERGE_LOG = LOGS_DIR / "merge_log.json"


# ─── Git Operations ───────────────────────────────────────

def run_git(*args: str, cwd: str = ".") -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    result = subprocess.run(
        ["git"] + list(args),
        capture_output=True, text=True, cwd=cwd
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def get_current_branch() -> str:
    """Get the current branch name."""
    code, out, _ = run_git("rev-parse", "--abbrev-ref", "HEAD")
    return out if code == 0 else "unknown"


def branch_exists(branch: str) -> bool:
    """Check if a branch exists."""
    code, _, _ = run_git("rev-parse", "--verify", branch)
    return code == 0


def merge_branch(branch: str, message: str = "") -> tuple[bool, str]:
    """
    Merge a branch into the current branch.
    Returns (success, output).
    """
    if not message:
        message = f"Merge {branch} into {get_current_branch()}"

    code, out, err = run_git("merge", branch, "--no-ff", "-m", message)
    if code != 0:
        return False, f"Merge failed: {err or out}"
    return True, out


def abort_merge() -> None:
    """Abort an in-progress merge."""
    run_git("merge", "--abort")


def get_merge_diff(branch: str) -> str:
    """Get diff stats for a branch."""
    code, out, _ = run_git("diff", "--stat", f"main...{branch}")
    return out if code == 0 else "(no diff available)"


# ─── Test Runner ──────────────────────────────────────────

def run_tests(test_type: str = "all") -> tuple[bool, str]:
    """
    Run test suite after a merge.
    Returns (success, output).
    """
    results = []
    success = True

    # Backend tests (pytest)
    if test_type in ("all", "backend"):
        backend_test_path = Path("app/backend")
        if backend_test_path.exists():
            code, out, err = _run_command("python", "-m", "pytest", str(backend_test_path), "-v", "--tb=short")
            results.append(f"Backend tests: {'PASS' if code == 0 else 'FAIL'}\n{out or err}")
            if code != 0:
                success = False

    # Frontend tests (npm)
    if test_type in ("all", "frontend"):
        frontend_path = Path("app/frontend")
        if frontend_path.exists() and (frontend_path / "package.json").exists():
            code, out, err = _run_command("npm", "test", "--prefix", str(frontend_path))
            results.append(f"Frontend tests: {'PASS' if code == 0 else 'FAIL'}\n{out or err}")
            if code != 0:
                success = False

    # E2E tests (Playwright)
    if test_type in ("all", "e2e"):
        tests_path = Path("app/tests")
        if tests_path.exists():
            code, out, err = _run_command("npx", "playwright", "test", "--reporter=line",
                                          cwd=str(tests_path))
            results.append(f"E2E tests: {'PASS' if code == 0 else 'FAIL'}\n{out or err}")
            if code != 0:
                success = False

    if not results:
        return True, "(No tests found — skipping)"

    return success, "\n".join(results)


def _run_command(*args: str, cwd: str = ".") -> tuple[int, str, str]:
    """Run a shell command."""
    try:
        result = subprocess.run(
            list(args), capture_output=True, text=True, cwd=cwd, timeout=120
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 1, "", f"Command not found: {args[0]}"
    except subprocess.TimeoutExpired:
        return 1, "", "Command timed out (120s)"


# ─── Git Bisect ───────────────────────────────────────────

def run_bisect(branch: str, test_cmd: str = "python -m pytest") -> dict:
    """
    Run git bisect to find the breaking commit on a branch.
    Returns info about the breaking commit.
    """
    print(f"    🔍 Running git bisect on {branch}...")

    # Get base commit (merge base with main)
    code, merge_base, _ = run_git("merge-base", "main", branch)
    if code != 0:
        return {"error": "Could not find merge base"}

    code, branch_head, _ = run_git("rev-parse", branch)
    if code != 0:
        return {"error": f"Could not resolve {branch}"}

    # Start bisect
    run_git("bisect", "start")
    run_git("bisect", "bad", branch_head)
    run_git("bisect", "good", merge_base)

    # Run bisect with test command
    code, out, err = run_git("bisect", "run", *test_cmd.split())

    # Get the result
    code2, bisect_result, _ = run_git("bisect", "log")

    # Clean up
    run_git("bisect", "reset")

    return {
        "branch": branch,
        "merge_base": merge_base[:8],
        "branch_head": branch_head[:8],
        "bisect_log": bisect_result,
        "breaking_commit": out if code == 0 else "unknown",
    }


def construct_fix_prompt(branch: str, test_output: str, bisect_result: dict) -> str:
    """Construct a fix prompt for the responsible agent."""
    return f"""## Fix Required — Merge Failure

Your branch `{branch}` caused test failures after merging into main.

### Test Output:
```
{test_output}
```

### Bisect Result:
- Breaking commit range: {bisect_result.get('merge_base', '?')}..{bisect_result.get('branch_head', '?')}
- Bisect log: {bisect_result.get('bisect_log', 'N/A')}

### Instructions:
1. Identify the root cause from the test output above
2. Fix the issue in your directory ONLY
3. Ensure all tests pass
4. Create a new `.agent_complete` sentinel when done

Do NOT modify files outside your assigned directory.
"""


# ─── Merge Coordinator ───────────────────────────────────

class MergeCoordinator:
    """Coordinates topological merge of agent branches."""

    def __init__(self, manifest_path: str, demo_mode: bool = False):
        self.dag = DagOrchestrator.from_manifest(manifest_path)
        self.demo_mode = demo_mode
        self.merge_log: list[dict] = []

    def run(self) -> bool:
        """
        Execute topological merge.
        Returns True if all merges succeed.
        """
        order = self.dag.get_topological_order()
        tasks = {t["task_id"]: t for t in self.dag.get_all_tasks()}

        print("\n" + "=" * 60)
        print("  PolyAgent CI — Merge Coordinator")
        print("=" * 60)
        print(f"\n  Merge order: {' → '.join(order)}")
        print()

        # Ensure we're on main
        current = get_current_branch()
        if current != "main":
            print(f"  ⚠️  Currently on '{current}', switching to main...")
            run_git("checkout", "main")

        all_success = True

        for i, task_id in enumerate(order, 1):
            task = tasks[task_id]
            branch = task["branch"]
            agent = task["agent"]

            print(f"\n{'─' * 60}")
            print(f"  [{i}/{len(order)}] Merging: {branch} ({agent})")
            print(f"{'─' * 60}")

            # Check branch exists
            if not self.demo_mode and not branch_exists(branch):
                print(f"    ⚠️  Branch '{branch}' not found, skipping...")
                self._log_merge(task_id, branch, "skipped", "Branch not found")
                continue

            if self.demo_mode:
                # Simulate merge
                print(f"    [DEMO] Simulating merge of {branch}...")
                self._log_merge(task_id, branch, "success", "Demo mode — simulated merge")
                print(f"    ✅ Merge successful (simulated)")

                # Simulate test run
                print(f"    🧪 Running tests after merge...")
                print(f"    ✅ Tests passed (simulated)")
                self._log_merge(task_id, branch, "tests_passed", "Demo mode — simulated tests")
                continue

            # Real merge
            diff_stats = get_merge_diff(branch)
            print(f"    📊 Changes:\n{_indent(diff_stats, 8)}")

            success, merge_output = merge_branch(
                branch,
                f"[PolyAgent CI] Merge {branch} ({task_id}) — step {i}/{len(order)}"
            )

            if not success:
                print(f"    ❌ Merge failed: {merge_output}")
                abort_merge()
                self._log_merge(task_id, branch, "merge_failed", merge_output)
                all_success = False

                # Construct fix prompt
                fix = construct_fix_prompt(branch, merge_output, {})
                fix_path = LOGS_DIR / f"fix_prompt_{task_id}.md"
                fix_path.write_text(fix)
                print(f"    📝 Fix prompt saved to: {fix_path}")
                continue

            print(f"    ✅ Merge successful")
            self._log_merge(task_id, branch, "merged", merge_output)

            # Run tests after merge
            print(f"    🧪 Running tests after merge...")
            test_success, test_output = run_tests()

            if not test_success:
                print(f"    ❌ Tests failed after merging {branch}")
                print(f"    📋 Test output:\n{_indent(test_output, 8)}")
                self._log_merge(task_id, branch, "tests_failed", test_output)

                # Run bisect
                bisect_result = run_bisect(branch)
                fix = construct_fix_prompt(branch, test_output, bisect_result)
                fix_path = LOGS_DIR / f"fix_prompt_{task_id}.md"
                fix_path.write_text(fix)
                print(f"    📝 Fix prompt saved to: {fix_path}")

                all_success = False
            else:
                print(f"    ✅ Tests passed")
                self._log_merge(task_id, branch, "tests_passed", test_output[:500])

        # Summary
        print(f"\n{'=' * 60}")
        if all_success:
            print("  🎉 All merges complete and tests passing!")
            # Tag the merge point
            if not self.demo_mode:
                tag_name = f"polyagent-ci-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                run_git("tag", tag_name)
                print(f"  🏷️  Tagged: {tag_name}")
        else:
            print("  ⚠️  Some merges or tests failed. Check fix prompts in logs/")
        print(f"{'=' * 60}")

        self._save_log()
        return all_success

    def _log_merge(self, task_id: str, branch: str, status: str, details: str) -> None:
        self.merge_log.append({
            "timestamp": datetime.now().isoformat(),
            "task_id": task_id,
            "branch": branch,
            "status": status,
            "details": details[:1000],
        })

    def _save_log(self) -> None:
        with open(MERGE_LOG, "w") as f:
            json.dump(self.merge_log, f, indent=2)
        print(f"\n  📋 Merge log saved to: {MERGE_LOG}")


def _indent(text: str, spaces: int) -> str:
    """Indent each line of text."""
    prefix = " " * spaces
    return "\n".join(prefix + line for line in text.split("\n"))


# ─── CLI ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="PolyAgent CI — Merge Coordinator")
    parser.add_argument("--manifest", required=True, help="Path to manifest JSON")
    parser.add_argument("--demo-mode", action="store_true", help="Simulate merges")
    parser.add_argument("--skip-tests", action="store_true", help="Skip test runs after merge")
    args = parser.parse_args()

    coordinator = MergeCoordinator(args.manifest, demo_mode=args.demo_mode)
    success = coordinator.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
