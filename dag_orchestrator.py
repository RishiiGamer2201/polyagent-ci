"""
PolyAgent CI — DAG Orchestrator

Implements Kahn's algorithm for topological task scheduling.
Manages task lifecycle: PENDING → RUNNING → COMPLETE.
Provides get_ready_tasks() for parallel execution and mark_complete() for progress.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any
from collections import defaultdict


class TaskState(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class CycleDetectedError(Exception):
    """Raised when the task dependency graph contains a cycle."""
    pass


class TaskNotFoundError(Exception):
    """Raised when referencing a task_id that doesn't exist."""
    pass


class DagOrchestrator:
    """
    Directed Acyclic Graph orchestrator using Kahn's algorithm.

    Usage:
        dag = DagOrchestrator.from_manifest("manifests/manifest.json")
        while not dag.is_done():
            ready = dag.get_ready_tasks()
            for task in ready:
                dag.mark_running(task["task_id"])
                # launch agent...
            # wait for completion...
            dag.mark_complete(completed_task_id)
    """

    def __init__(self, tasks: list[dict[str, Any]]):
        """
        Initialize from a list of task dicts.
        Each task must have: task_id, description, agent, branch, depends_on (list).
        """
        self._tasks: dict[str, dict[str, Any]] = {}
        self._state: dict[str, TaskState] = {}
        self._dependents: dict[str, list[str]] = defaultdict(list)  # task → [tasks that depend on it]
        self._dependency_count: dict[str, int] = {}  # task → number of unmet dependencies

        # Index tasks
        for task in tasks:
            tid = task["task_id"]
            self._tasks[tid] = task
            self._state[tid] = TaskState.PENDING
            self._dependency_count[tid] = len(task.get("depends_on", []))

        # Build reverse adjacency (dependents map)
        for task in tasks:
            tid = task["task_id"]
            for dep in task.get("depends_on", []):
                if dep not in self._tasks:
                    raise TaskNotFoundError(
                        f"Task '{tid}' depends on '{dep}', which doesn't exist in the manifest."
                    )
                self._dependents[dep].append(tid)

        # Validate: detect cycles via DFS
        self._detect_cycles()

    @classmethod
    def from_manifest(cls, manifest_path: str) -> "DagOrchestrator":
        """Load from a manifest JSON file."""
        with open(manifest_path, "r") as f:
            data = json.load(f)

        tasks = data if isinstance(data, list) else data.get("tasks", [])
        return cls(tasks)

    @classmethod
    def from_json(cls, json_str: str) -> "DagOrchestrator":
        """Load from a JSON string."""
        data = json.loads(json_str)
        tasks = data if isinstance(data, list) else data.get("tasks", [])
        return cls(tasks)

    # ─── Cycle Detection (DFS) ────────────────────────────

    def _detect_cycles(self) -> None:
        """DFS-based cycle detection. Raises CycleDetectedError if cycle found."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {tid: WHITE for tid in self._tasks}
        path: list[str] = []

        def dfs(tid: str) -> None:
            color[tid] = GRAY
            path.append(tid)

            for dep_tid in self._dependents.get(tid, []):
                if color[dep_tid] == GRAY:
                    # Found a cycle — extract it
                    cycle_start = path.index(dep_tid)
                    cycle = path[cycle_start:] + [dep_tid]
                    raise CycleDetectedError(
                        f"Dependency cycle detected: {' → '.join(cycle)}"
                    )
                if color[dep_tid] == WHITE:
                    dfs(dep_tid)

            path.pop()
            color[tid] = BLACK

        for tid in self._tasks:
            if color[tid] == WHITE:
                dfs(tid)

    # ─── Core API ─────────────────────────────────────────

    def get_ready_tasks(self) -> list[dict[str, Any]]:
        """
        Returns tasks whose dependencies are ALL complete AND are still PENDING.
        These can be launched in parallel (Kahn's frontier).
        """
        ready = []
        for tid, task in self._tasks.items():
            if self._state[tid] != TaskState.PENDING:
                continue
            # Check all dependencies are complete
            deps = task.get("depends_on", [])
            if all(self._state[dep] == TaskState.COMPLETE for dep in deps):
                ready.append(task)
        return ready

    def mark_running(self, task_id: str) -> None:
        """Mark a task as currently running."""
        if task_id not in self._tasks:
            raise TaskNotFoundError(f"Task '{task_id}' not found.")
        self._state[task_id] = TaskState.RUNNING

    def mark_complete(self, task_id: str) -> list[dict[str, Any]]:
        """
        Mark a task as complete. Returns newly unlocked tasks (if any).
        """
        if task_id not in self._tasks:
            raise TaskNotFoundError(f"Task '{task_id}' not found.")
        self._state[task_id] = TaskState.COMPLETE

        # Find newly unlocked tasks
        newly_ready = []
        for dependent_id in self._dependents.get(task_id, []):
            if self._state[dependent_id] != TaskState.PENDING:
                continue
            dep_task = self._tasks[dependent_id]
            deps = dep_task.get("depends_on", [])
            if all(self._state[d] == TaskState.COMPLETE for d in deps):
                newly_ready.append(dep_task)

        return newly_ready

    def mark_failed(self, task_id: str) -> None:
        """Mark a task as failed."""
        if task_id not in self._tasks:
            raise TaskNotFoundError(f"Task '{task_id}' not found.")
        self._state[task_id] = TaskState.FAILED

    def is_done(self) -> bool:
        """Returns True when all tasks are COMPLETE."""
        return all(s == TaskState.COMPLETE for s in self._state.values())

    def has_failed(self) -> bool:
        """Returns True if any task has FAILED."""
        return any(s == TaskState.FAILED for s in self._state.values())

    def get_status(self) -> dict[str, dict[str, Any]]:
        """Returns a dict of {task_id: {state, agent, branch, description}}."""
        result = {}
        for tid, task in self._tasks.items():
            result[tid] = {
                "state": self._state[tid].value,
                "agent": task.get("agent", "unknown"),
                "branch": task.get("branch", "unknown"),
                "description": task.get("description", ""),
                "depends_on": task.get("depends_on", []),
            }
        return result

    def get_topological_order(self) -> list[str]:
        """
        Returns tasks in topological order (for merge ordering).
        Uses Kahn's algorithm to produce a valid linear ordering.
        """
        in_degree = {}
        for tid, task in self._tasks.items():
            in_degree[tid] = len(task.get("depends_on", []))

        queue = [tid for tid, deg in in_degree.items() if deg == 0]
        order = []

        while queue:
            # Sort for deterministic output
            queue.sort()
            tid = queue.pop(0)
            order.append(tid)

            for dependent_id in self._dependents.get(tid, []):
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    queue.append(dependent_id)

        return order

    def get_task(self, task_id: str) -> dict[str, Any]:
        """Get a single task by ID."""
        if task_id not in self._tasks:
            raise TaskNotFoundError(f"Task '{task_id}' not found.")
        return self._tasks[task_id]

    def get_all_tasks(self) -> list[dict[str, Any]]:
        """Get all tasks."""
        return list(self._tasks.values())

    def __repr__(self) -> str:
        states = {tid: s.value for tid, s in self._state.items()}
        return f"DagOrchestrator(tasks={len(self._tasks)}, states={states})"
