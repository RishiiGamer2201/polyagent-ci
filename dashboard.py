"""
PolyAgent CI — Terminal Dashboard (Demo Centerpiece)

Live terminal dashboard using Rich. Shows:
- Agent epistemic states (SPECULATING / CONFIRMED / DIVERGED / RECONCILING)
- DAG visualization with current frontier
- Scrolling event log
- Overall progress

Usage:
    python dashboard.py                          # Live mode (reads logs/)
    python dashboard.py --demo-mode              # Animated demo
    python dashboard.py --demo-mode --timeout 30 # Auto-exit after 30s
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import threading
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree
from rich.progress import Progress, BarColumn, TextColumn, SpinnerColumn
from rich.align import Align
from rich import box

# ─── Constants ────────────────────────────────────────────

LOGS_DIR = Path("logs")
DAG_STATE_FILE = LOGS_DIR / "dag_state.json"
EVENTS_FILE = LOGS_DIR / "agent_events.json"
REVIEW_LOG = LOGS_DIR / "review_log.json"

REFRESH_RATE = 1  # seconds

# Epistemic state definitions
EPISTEMIC_STATES = {
    "SPECULATING":  ("🔵", "bold blue",    "Working with assumptions"),
    "CONFIRMED":    ("🟢", "bold green",   "Output validated against contracts"),
    "DIVERGED":     ("🔴", "bold red",     "Conflict detected with another agent"),
    "RECONCILING":  ("🟡", "bold yellow",  "Applying fix after conflict"),
    "PENDING":      ("⚪", "dim",          "Not started yet"),
    "RUNNING":      ("🔵", "bold cyan",    "Agent is working"),
    "COMPLETE":     ("🟢", "bold green",   "Task finished"),
    "FAILED":       ("🔴", "bold red",     "Task failed"),
}

# Agent display names
AGENT_INFO = {
    "frontend": {"name": "Frontend Agent", "icon": "🎨", "dir": "/app/frontend/"},
    "backend":  {"name": "Backend Agent",  "icon": "⚙️",  "dir": "/app/backend/"},
    "crdt":     {"name": "CRDT Agent",     "icon": "🔄", "dir": "/app/crdt/"},
    "qa":       {"name": "QA Agent",       "icon": "🧪", "dir": "/app/tests/"},
}


# ─── Data Sources ─────────────────────────────────────────

class DashboardData:
    """Reads and caches state from log files."""

    def __init__(self):
        self.dag_state: dict = {}
        self.events: list[dict] = []
        self.review_results: list[dict] = []
        self.epistemic_states: dict[str, str] = {
            "frontend": "PENDING",
            "backend": "PENDING",
            "crdt": "PENDING",
            "qa": "PENDING",
        }

    def refresh(self) -> None:
        """Re-read all log files."""
        self._read_dag_state()
        self._read_events()
        self._read_reviews()
        self._compute_epistemic_states()

    def _read_dag_state(self) -> None:
        if DAG_STATE_FILE.exists():
            try:
                with open(DAG_STATE_FILE) as f:
                    self.dag_state = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                pass

    def _read_events(self) -> None:
        if EVENTS_FILE.exists():
            try:
                with open(EVENTS_FILE) as f:
                    self.events = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                pass

    def _read_reviews(self) -> None:
        if REVIEW_LOG.exists():
            try:
                with open(REVIEW_LOG) as f:
                    self.review_results = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                pass

    def _compute_epistemic_states(self) -> None:
        """
        Compute epistemic state for each agent based on:
        - DAG state (PENDING/RUNNING/COMPLETE)
        - Review results (DIVERGED if conflicts found)
        """
        tasks = self.dag_state.get("tasks", {})

        for task_id in ["frontend", "backend", "crdt", "qa"]:
            task_info = tasks.get(task_id, {})
            dag_state = task_info.get("state", "PENDING")

            # Check review results for this task
            has_conflict = False
            is_reconciling = False
            for review in self.review_results:
                if review.get("task_id") == task_id:
                    if review.get("status") == "fail":
                        has_conflict = True
                    elif review.get("status") == "pass" and has_conflict:
                        is_reconciling = False

            # Determine epistemic state
            if is_reconciling:
                self.epistemic_states[task_id] = "RECONCILING"
            elif has_conflict:
                self.epistemic_states[task_id] = "DIVERGED"
            elif dag_state == "COMPLETE":
                self.epistemic_states[task_id] = "CONFIRMED"
            elif dag_state == "RUNNING":
                self.epistemic_states[task_id] = "SPECULATING"
            else:
                self.epistemic_states[task_id] = "PENDING"

    def get_progress(self) -> float:
        """Get overall completion percentage."""
        tasks = self.dag_state.get("tasks", {})
        if not tasks:
            return 0.0
        complete = sum(1 for t in tasks.values() if t.get("state") == "COMPLETE")
        return complete / len(tasks) * 100


# ─── Demo Data Generator ─────────────────────────────────

class DemoDataGenerator:
    """Generates animated demo data for the dashboard."""

    def __init__(self):
        self.tick = 0
        self.data = DashboardData()
        self._generate_initial_state()

    def _generate_initial_state(self) -> None:
        """Set up initial demo state."""
        self.data.dag_state = {
            "timestamp": datetime.now().isoformat(),
            "is_done": False,
            "tasks": {
                "frontend": {"state": "PENDING", "agent": "frontend-agent", "branch": "agent/frontend", "depends_on": []},
                "backend": {"state": "PENDING", "agent": "backend-agent", "branch": "agent/backend", "depends_on": []},
                "crdt": {"state": "PENDING", "agent": "crdt-agent", "branch": "agent/crdt", "depends_on": ["backend"]},
                "qa": {"state": "PENDING", "agent": "qa-agent", "branch": "agent/qa", "depends_on": ["frontend", "backend", "crdt"]},
            },
            "ready_tasks": ["frontend", "backend"],
            "topological_order": ["backend", "frontend", "crdt", "qa"],
        }
        self.data.events = []

    def advance(self) -> None:
        """Advance the demo by one tick."""
        self.tick += 1
        tasks = self.data.dag_state["tasks"]

        # Timeline:
        # tick 2: frontend + backend start
        if self.tick == 2:
            tasks["frontend"]["state"] = "RUNNING"
            tasks["backend"]["state"] = "RUNNING"
            self.data.dag_state["ready_tasks"] = []
            self._add_event("AGENT_LAUNCHED", "frontend", "Frontend Agent started on agent/frontend")
            self._add_event("AGENT_LAUNCHED", "backend", "Backend Agent started on agent/backend")
            self.data.epistemic_states["frontend"] = "SPECULATING"
            self.data.epistemic_states["backend"] = "SPECULATING"

        # tick 6: backend completes, crdt starts
        elif self.tick == 6:
            tasks["backend"]["state"] = "COMPLETE"
            self._add_event("TASK_COMPLETE", "backend", "Backend Agent completed successfully")
            self.data.epistemic_states["backend"] = "CONFIRMED"
            tasks["crdt"]["state"] = "RUNNING"
            self.data.dag_state["ready_tasks"] = []
            self._add_event("TASK_UNLOCKED", "crdt", "Unlocked by: backend")
            self._add_event("AGENT_LAUNCHED", "crdt", "CRDT Agent started on agent/crdt")
            self.data.epistemic_states["crdt"] = "SPECULATING"

        # tick 8: frontend completes
        elif self.tick == 8:
            tasks["frontend"]["state"] = "COMPLETE"
            self._add_event("TASK_COMPLETE", "frontend", "Frontend Agent completed successfully")
            self.data.epistemic_states["frontend"] = "CONFIRMED"

        # tick 9: review agent catches conflict on frontend
        elif self.tick == 9:
            self._add_event("REVIEW_START", "frontend", "Review Agent analyzing frontend branch...")
            self.data.review_results.append({
                "task_id": "frontend",
                "status": "fail",
                "conflicts": [
                    {
                        "severity": "critical",
                        "category": "endpoint_mismatch",
                        "description": "Frontend uses '/api/docs' instead of '/documents'",
                    }
                ],
                "summary": "CRITICAL: Endpoint mismatch /api/docs vs /documents"
            })
            self.data.epistemic_states["frontend"] = "DIVERGED"
            self._add_event("CONFLICT_FOUND", "frontend",
                            "🔴 CRITICAL: Endpoint mismatch — /api/docs vs /documents")

        # tick 11: conflict auto-resolved
        elif self.tick == 11:
            self._add_event("CONFLICT_RESOLVED", "frontend",
                            "Auto-applied fix: /api/docs → /documents")
            self.data.epistemic_states["frontend"] = "RECONCILING"

        # tick 12: frontend re-confirmed
        elif self.tick == 12:
            self.data.epistemic_states["frontend"] = "CONFIRMED"
            self._add_event("REVIEW_PASS", "frontend", "Frontend re-validated — all contracts match")

        # tick 13: crdt completes, qa unlocked
        elif self.tick == 13:
            tasks["crdt"]["state"] = "COMPLETE"
            self._add_event("TASK_COMPLETE", "crdt", "CRDT Agent completed successfully")
            self.data.epistemic_states["crdt"] = "CONFIRMED"
            tasks["qa"]["state"] = "RUNNING"
            self._add_event("TASK_UNLOCKED", "qa", "Unlocked by: frontend, backend, crdt")
            self._add_event("AGENT_LAUNCHED", "qa", "QA Agent started on agent/qa")
            self.data.epistemic_states["qa"] = "SPECULATING"

        # tick 18: qa completes
        elif self.tick == 18:
            tasks["qa"]["state"] = "COMPLETE"
            self.data.dag_state["is_done"] = True
            self._add_event("TASK_COMPLETE", "qa", "QA Agent completed — all tests passing")
            self.data.epistemic_states["qa"] = "CONFIRMED"

        # tick 19: merge sequence
        elif self.tick == 19:
            self._add_event("MERGE_START", "all", "Starting topological merge: backend → crdt → frontend → qa")

        elif self.tick == 20:
            self._add_event("MERGE_SUCCESS", "backend", "✅ Merged agent/backend into main — tests pass")

        elif self.tick == 21:
            self._add_event("MERGE_SUCCESS", "crdt", "✅ Merged agent/crdt into main — tests pass")

        elif self.tick == 22:
            self._add_event("MERGE_SUCCESS", "frontend", "✅ Merged agent/frontend into main — tests pass")

        elif self.tick == 23:
            self._add_event("MERGE_SUCCESS", "qa", "✅ Merged agent/qa into main — all E2E tests pass")
            self._add_event("PIPELINE_DONE", "all", "🎉 Pipeline complete! Collaborative editor ready.")

        # Update progress tracking
        self.data.dag_state["ready_tasks"] = [
            tid for tid, t in tasks.items() if t["state"] == "PENDING"
        ]
        self.data.refresh = lambda: None  # No-op for demo

    def _add_event(self, event_type: str, task_id: str, details: str) -> None:
        self.data.events.append({
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "task_id": task_id,
            "details": details,
        })


# ─── Dashboard Renderers ─────────────────────────────────

def make_header() -> Panel:
    """Create the header panel."""
    header_text = Text()
    header_text.append("◆ ", style="bold magenta")
    header_text.append("POLYAGENT CI", style="bold white")
    header_text.append("  │  ", style="dim")
    header_text.append("Multi-Agent Orchestration Dashboard", style="italic cyan")
    header_text.append("  │  ", style="dim")
    header_text.append(datetime.now().strftime("%H:%M:%S"), style="dim green")

    return Panel(
        Align.center(header_text),
        style="bold blue",
        box=box.DOUBLE,
    )


def make_agent_panel(data: DashboardData) -> Panel:
    """Create the agent status panel with epistemic states."""
    table = Table(
        show_header=True, header_style="bold magenta",
        box=box.SIMPLE_HEAVY, expand=True,
        title="Agent Status", title_style="bold white",
    )
    table.add_column("Agent",    style="bold",    no_wrap=True)
    table.add_column("Dir",      style="dim",     no_wrap=True, max_width=12)
    table.add_column("State",    justify="center", no_wrap=True)
    table.add_column("Epistemic",justify="center", no_wrap=True)

    for task_id in ["frontend", "backend", "crdt", "qa"]:
        info = AGENT_INFO.get(task_id, {"name": task_id, "icon": "❓", "dir": "?"})
        tasks = data.dag_state.get("tasks", {})
        task_data = tasks.get(task_id, {})
        dag_state = task_data.get("state", "PENDING")
        epistemic = data.epistemic_states.get(task_id, "PENDING")

        # DAG state badge
        state_icon, state_style, _ = EPISTEMIC_STATES.get(dag_state, ("❓", "dim", ""))
        state_text = Text(f"{state_icon} {dag_state}", style=state_style)

        # Epistemic state badge
        ep_icon, ep_style, ep_desc = EPISTEMIC_STATES.get(epistemic, ("❓", "dim", ""))
        ep_text = Text(f"{ep_icon} {epistemic}", style=ep_style)

        table.add_row(
            f"{info['icon']} {info['name']}",
            info["dir"],
            state_text,
            ep_text,
        )

    return Panel(table, border_style="blue")


def make_dag_panel(data: DashboardData) -> Panel:
    """Create the DAG visualization panel."""
    tasks = data.dag_state.get("tasks", {})
    ready = set(data.dag_state.get("ready_tasks", []))

    # Build ASCII DAG
    dag_text = Text()
    dag_text.append("Task Dependency Graph\n\n", style="bold white")

    # Visual layout
    nodes = {
        "frontend": {"col": 0, "row": 0},
        "backend":  {"col": 1, "row": 0},
        "crdt":     {"col": 1, "row": 1},
        "qa":       {"col": 0, "row": 2},
    }

    # Row 0: Frontend and Backend (parallel)
    for task_id in ["frontend", "backend"]:
        state = tasks.get(task_id, {}).get("state", "PENDING")
        icon, style, _ = EPISTEMIC_STATES.get(state, ("❓", "dim", ""))
        marker = "►" if task_id in ready else icon
        dag_text.append(f"  [{marker} {task_id}]", style=style)
        dag_text.append("    ", style="dim")
    dag_text.append("\n")

    # Connector lines
    dag_text.append("       │            │\n", style="dim")
    dag_text.append("       │            ▼\n", style="dim")

    # Row 1: CRDT (depends on backend)
    state = tasks.get("crdt", {}).get("state", "PENDING")
    icon, style, _ = EPISTEMIC_STATES.get(state, ("❓", "dim", ""))
    marker = "►" if "crdt" in ready else icon
    dag_text.append(f"       │      [{marker} crdt]\n", style=style)

    # Connector to QA
    dag_text.append("       │            │\n", style="dim")
    dag_text.append("       └────────────┤\n", style="dim")
    dag_text.append("                    ▼\n", style="dim")

    # Row 2: QA (depends on all)
    state = tasks.get("qa", {}).get("state", "PENDING")
    icon, style, _ = EPISTEMIC_STATES.get(state, ("❓", "dim", ""))
    marker = "►" if "qa" in ready else icon
    dag_text.append(f"              [{marker} qa]\n", style=style)

    # Progress
    progress = data.get_progress()
    dag_text.append(f"\n  Progress: ", style="dim")
    filled = int(progress / 5)
    dag_text.append("█" * filled, style="bold green")
    dag_text.append("░" * (20 - filled), style="dim")
    dag_text.append(f" {progress:.0f}%\n", style="bold white")

    return Panel(dag_text, title="DAG", border_style="cyan", title_align="left")


def make_event_log(data: DashboardData, max_events: int = 12) -> Panel:
    """Create the scrolling event log panel."""
    events = data.events[-max_events:]  # Last N events

    if not events:
        content = Text("  Waiting for events...", style="dim italic")
    else:
        content = Text()
        for event in events:
            ts = event.get("timestamp", "")
            if ts:
                # Extract just time
                try:
                    dt = datetime.fromisoformat(ts)
                    ts_short = dt.strftime("%H:%M:%S")
                except ValueError:
                    ts_short = ts[-8:]
            else:
                ts_short = "??:??:??"

            event_type = event.get("event_type", "")
            task_id = event.get("task_id", "")
            details = event.get("details", "")

            # Event type icons and colors
            type_config = {
                "AGENT_LAUNCHED": ("🚀", "cyan"),
                "TASK_STARTED": ("▶️", "cyan"),
                "TASK_COMPLETE": ("✅", "green"),
                "TASK_FAILED": ("❌", "red"),
                "TASK_UNLOCKED": ("🔓", "yellow"),
                "REVIEW_START": ("🔍", "blue"),
                "CONFLICT_FOUND": ("💥", "bold red"),
                "CONFLICT_RESOLVED": ("🔧", "yellow"),
                "REVIEW_PASS": ("✅", "green"),
                "MERGE_START": ("🔀", "magenta"),
                "MERGE_SUCCESS": ("✅", "green"),
                "PIPELINE_DONE": ("🎉", "bold green"),
                "POLL": ("👁", "dim"),
            }

            icon, color = type_config.get(event_type, ("📋", "white"))

            content.append(f"  {ts_short} ", style="dim")
            content.append(f"{icon} ", style=color)
            content.append(f"[{task_id}] ", style="bold")
            content.append(f"{details}\n", style=color)

    return Panel(
        content,
        title="Event Log",
        border_style="yellow",
        title_align="left",
    )


def make_review_panel(data: DashboardData) -> Panel:
    """Create the review results panel."""
    reviews = data.review_results

    if not reviews:
        content = Text("  No reviews yet...", style="dim italic")
    else:
        content = Text()
        for review in reviews[-4:]:
            task_id = review.get("task_id", "?")
            status = review.get("status", "?")
            summary = review.get("summary", "")

            status_style = {
                "pass": "bold green",
                "fail": "bold red",
                "warning": "bold yellow",
            }.get(status, "dim")

            status_icon = {"pass": "✅", "fail": "❌", "warning": "⚠️"}.get(status, "❓")

            content.append(f"  {status_icon} ", style=status_style)
            content.append(f"{task_id}: ", style="bold")
            content.append(f"{summary}\n", style=status_style)

            # Show conflicts
            for conflict in review.get("conflicts", []):
                sev = conflict.get("severity", "?")
                desc = conflict.get("description", "")
                sev_icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(sev, "⚪")
                content.append(f"     {sev_icon} {desc}\n", style="dim")

    return Panel(
        content,
        title="Review Results",
        border_style="red",
        title_align="left",
    )


def make_layout(data: DashboardData) -> Layout:
    """Create the full dashboard layout."""
    layout = Layout()

    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )

    layout["body"].split_row(
        Layout(name="left", ratio=1),
        Layout(name="right", ratio=1),
    )

    layout["left"].split_column(
        Layout(name="agents", ratio=2),
        Layout(name="reviews", ratio=1),
    )

    layout["right"].split_column(
        Layout(name="dag", ratio=1),
        Layout(name="events", ratio=2),
    )

    # Render panels
    layout["header"].update(make_header())
    layout["agents"].update(make_agent_panel(data))
    layout["dag"].update(make_dag_panel(data))
    layout["events"].update(make_event_log(data))
    layout["reviews"].update(make_review_panel(data))

    # Footer
    elapsed = int(time.time() - _start_time)
    seq_estimate = 240  # 4 hrs sequential
    footer_text = Text()
    footer_text.append("  [q]", style="bold yellow")
    footer_text.append(" quit  ", style="dim")
    footer_text.append("[d]", style="bold yellow")
    footer_text.append(" demo  ", style="dim")
    footer_text.append("│  ", style="dim")
    progress = data.get_progress()
    footer_text.append(f"Pipeline: {progress:.0f}% ", style="bold green" if progress >= 100 else "bold cyan")
    footer_text.append("│  ", style="dim")
    footer_text.append(f"Parallel: {elapsed//60}m{elapsed%60:02d}s", style="bold green")
    footer_text.append("  vs  ", style="dim")
    footer_text.append(f"Sequential: ~{seq_estimate//60}m  ", style="dim red")
    layout["footer"].update(Panel(footer_text, style="dim"))

    return layout


# ─── Main ─────────────────────────────────────────────────

_start_time = time.time()

def run_dashboard(demo_mode: bool = False, timeout: int = 0) -> None:
    """Run the live dashboard."""
    global _start_time
    console = Console()

    # Minimum width check
    if console.width < 100:
        console.print("[bold yellow]Warning:[/bold yellow] Terminal width is narrow. Run in a wider window for best results (100+ cols recommended).")
        time.sleep(1)

    if demo_mode:
        demo = DemoDataGenerator()
        data = demo.data
    else:
        data = DashboardData()
        data.refresh()  # Load existing logs immediately

    start_time = time.time()

    try:
        with Live(make_layout(data), refresh_per_second=1, console=console, screen=True) as live:
            while True:
                if demo_mode:
                    demo.advance()
                else:
                    data.refresh()

                live.update(make_layout(data))

                # Check timeout
                if timeout > 0 and (time.time() - start_time) > timeout:
                    break

                # Check if pipeline is done (in demo, wait a few more ticks)
                if demo_mode and demo.tick > 25:
                    break

                time.sleep(REFRESH_RATE)

    except KeyboardInterrupt:
        pass

    console.print("\n[bold green]Dashboard closed.[/bold green]")


def main():
    parser = argparse.ArgumentParser(description="PolyAgent CI — Dashboard")
    parser.add_argument("--demo-mode", action="store_true",
                        help="Run with animated demo data")
    parser.add_argument("--timeout", type=int, default=0,
                        help="Auto-exit after N seconds (0 = no timeout)")
    args = parser.parse_args()

    run_dashboard(demo_mode=args.demo_mode, timeout=args.timeout)


if __name__ == "__main__":
    main()
