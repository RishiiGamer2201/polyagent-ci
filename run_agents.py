"""
PolyAgent CI — Agent Runner

Reads ready tasks from DagOrchestrator, launches DevSwarm Builder sessions
simultaneously via subprocess, polls for .agent_complete sentinel files,
and launches newly unlocked tasks on completion.

Usage:
    python run_agents.py --manifest manifests/manifest_*.json
    python run_agents.py --manifest manifests/manifest_*.json --demo-mode
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from dag_orchestrator import DagOrchestrator, TaskState

load_dotenv()

# ─── Constants ────────────────────────────────────────────

POLL_INTERVAL = 5  # seconds
WORKTREE_DIR = Path("worktrees")
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)
PROMPTS_DIR = Path("prompts")

AGENT_PROMPT_MAP = {
    "frontend-agent": "frontend_prompt.md",
    "backend-agent": "backend_prompt.md",
    "crdt-agent": "crdt_prompt.md",
    "qa-agent": "qa_prompt.md",
}


# ─── Event Logger ─────────────────────────────────────────

class EventLogger:
    """Logs orchestrator events to JSON file for dashboard consumption."""

    def __init__(self, log_path: Path = LOGS_DIR / "agent_events.json"):
        self.log_path = log_path
        self.events: list[dict] = []
        if log_path.exists():
            try:
                with open(log_path) as f:
                    self.events = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                self.events = []

    def log(self, event_type: str, task_id: str, details: str = "", **kwargs) -> None:
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "task_id": task_id,
            "details": details,
            **kwargs,
        }
        self.events.append(event)
        self._flush()
        icon = {
            "TASK_STARTED": "🚀",
            "TASK_COMPLETE": "✅",
            "TASK_FAILED": "❌",
            "TASK_UNLOCKED": "🔓",
            "POLL": "👁️",
            "PIPELINE_DONE": "🎉",
            "AGENT_LAUNCHED": "🤖",
        }.get(event_type, "📋")
        print(f"  {icon} [{event_type}] {task_id}: {details}")

    def _flush(self) -> None:
        with open(self.log_path, "w") as f:
            json.dump(self.events, f, indent=2)


# ─── Agent Launcher ───────────────────────────────────────

class AgentLauncher:
    """Launches and monitors DevSwarm Builder sessions."""

    def __init__(self, demo_mode: bool = False):
        self.demo_mode = demo_mode
        self.processes: dict[str, subprocess.Popen] = {}
        self.logger = EventLogger()

    def launch_agent(self, task: dict) -> None:
        """Launch a DevSwarm Builder session for a task."""
        task_id = task["task_id"]
        agent = task["agent"]
        branch = task["branch"]
        safe_branch = branch.replace("/", "_")
        worktree_path = WORKTREE_DIR / safe_branch
        prompt_file = PROMPTS_DIR / AGENT_PROMPT_MAP.get(agent, f"{task_id}_prompt.md")

        self.logger.log("AGENT_LAUNCHED", task_id,
                        f"Agent: {agent}, Branch: {branch}, Worktree: {worktree_path}")

        if self.demo_mode:
            # Demo mode: simulate agent work with a background script
            self._launch_demo_agent(task_id, worktree_path)
        else:
            # Real mode: launch DevSwarm Builder
            self._launch_devswarm(task_id, worktree_path, prompt_file)

    def _launch_devswarm(self, task_id: str, worktree_path: Path, prompt_file: Path) -> None:
        """Launch a real DevSwarm Builder session."""
        cmd = [
            "devswarm", "build",
            "--worktree", str(worktree_path),
            "--prompt", str(prompt_file),
            "--agent-id", task_id,
        ]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(worktree_path),
            )
            self.processes[task_id] = proc
            self.logger.log("TASK_STARTED", task_id, f"PID: {proc.pid}")
        except FileNotFoundError:
            self.logger.log("TASK_FAILED", task_id,
                            "DevSwarm CLI not found. Install DevSwarm or use --demo-mode")
            raise

    def _launch_demo_agent(self, task_id: str, worktree_path: Path) -> None:
        """Simulate agent work for demo purposes."""
        # Create worktree dir if it doesn't exist (for demo)
        worktree_path.mkdir(parents=True, exist_ok=True)

        # Launch a background script that waits and creates the sentinel
        delay_map = {
            "frontend": 8,
            "backend": 6,
            "crdt": 5,
            "qa": 7,
        }
        delay = delay_map.get(task_id, 5)

        # PowerShell command to simulate work
        sentinel_path = worktree_path / ".agent_complete"
        sentinel_content = json.dumps({
            "task_id": task_id,
            "completed_at": "",  # Will be set by the script
            "status": "complete"
        })

        cmd = [
            "powershell", "-Command",
            f'Start-Sleep -Seconds {delay}; '
            f'$ts = Get-Date -Format "o"; '
            f'$content = \'{{"task_id": "{task_id}", "completed_at": "\' + $ts + \'", "status": "complete"}}\'; '
            f'Set-Content -Path "{sentinel_path}" -Value $content'
        ]

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.processes[task_id] = proc
        self.logger.log("TASK_STARTED", task_id,
                        f"[DEMO] Simulated agent, completes in ~{delay}s")

    def check_completion(self, task_id: str) -> bool:
        """Check if an agent has completed by looking for the sentinel file."""
        # Check all possible worktree locations
        for subdir in WORKTREE_DIR.iterdir() if WORKTREE_DIR.exists() else []:
            sentinel = subdir / ".agent_complete"
            if sentinel.exists():
                try:
                    data = json.loads(sentinel.read_text())
                    if data.get("task_id") == task_id:
                        return True
                except (json.JSONDecodeError, KeyError):
                    continue

        # Also check direct path
        task_dirs = {
            "frontend": "agent_frontend",
            "backend": "agent_backend",
            "crdt": "agent_crdt",
            "qa": "agent_qa",
        }
        direct_path = WORKTREE_DIR / task_dirs.get(task_id, f"agent_{task_id}") / ".agent_complete"
        if direct_path.exists():
            try:
                data = json.loads(direct_path.read_text())
                return data.get("task_id") == task_id
            except (json.JSONDecodeError, KeyError):
                pass

        return False

    def cleanup(self) -> None:
        """Terminate all running processes."""
        for task_id, proc in self.processes.items():
            if proc.poll() is None:
                proc.terminate()
                print(f"  🛑 Terminated agent: {task_id}")


# ─── Main Orchestration Loop ─────────────────────────────

def run_pipeline(manifest_path: str, demo_mode: bool = False) -> None:
    """Main orchestration loop."""
    print("=" * 60)
    print("  PolyAgent CI — Agent Runner")
    print("=" * 60)
    print()

    # Initialize
    dag = DagOrchestrator.from_manifest(manifest_path)
    launcher = AgentLauncher(demo_mode=demo_mode)
    running_tasks: set[str] = set()

    print(f"📋 Loaded manifest: {manifest_path}")
    print(f"📊 Total tasks: {len(dag.get_all_tasks())}")
    print(f"🎮 Mode: {'DEMO' if demo_mode else 'LIVE'}")
    print()

    # Save DAG state for dashboard
    _save_dag_state(dag)

    try:
        while not dag.is_done():
            # Get ready tasks
            ready = dag.get_ready_tasks()

            # Launch new tasks
            for task in ready:
                tid = task["task_id"]
                if tid not in running_tasks:
                    dag.mark_running(tid)
                    launcher.launch_agent(task)
                    running_tasks.add(tid)

            # Poll for completions
            completed_this_cycle = []
            for tid in list(running_tasks):
                if launcher.check_completion(tid):
                    launcher.logger.log("TASK_COMPLETE", tid, "Agent reported completion")
                    newly_unlocked = dag.mark_complete(tid)
                    running_tasks.discard(tid)
                    completed_this_cycle.append(tid)

                    for unlocked_task in newly_unlocked:
                        launcher.logger.log("TASK_UNLOCKED", unlocked_task["task_id"],
                                            f"Unlocked by: {tid}")

            # Update DAG state for dashboard
            if completed_this_cycle:
                _save_dag_state(dag)

            # Wait before next poll
            if not dag.is_done() and not completed_this_cycle:
                time.sleep(POLL_INTERVAL)

        # Pipeline complete
        launcher.logger.log("PIPELINE_DONE", "all", "All tasks completed successfully!")
        _save_dag_state(dag)

        print()
        print("=" * 60)
        print("  🎉 Pipeline Complete! All agents finished.")
        print("=" * 60)

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted! Cleaning up agents...")
        launcher.cleanup()
        _save_dag_state(dag)
        sys.exit(1)


def _save_dag_state(dag: DagOrchestrator) -> None:
    """Save current DAG state for dashboard consumption."""
    state_path = LOGS_DIR / "dag_state.json"
    state = {
        "timestamp": datetime.now().isoformat(),
        "is_done": dag.is_done(),
        "tasks": dag.get_status(),
        "topological_order": dag.get_topological_order(),
        "ready_tasks": [t["task_id"] for t in dag.get_ready_tasks()],
    }
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)


# ─── CLI ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="PolyAgent CI — Agent Runner")
    parser.add_argument("--manifest", required=True, help="Path to manifest JSON")
    parser.add_argument("--demo-mode", action="store_true",
                        help="Simulate agent work (no real DevSwarm)")
    parser.add_argument("--poll-interval", type=int, default=5,
                        help="Seconds between completion polls (default: 5)")
    args = parser.parse_args()

    global POLL_INTERVAL
    POLL_INTERVAL = args.poll_interval

    run_pipeline(args.manifest, demo_mode=args.demo_mode)


if __name__ == "__main__":
    main()
