"""
PolyAgent CI — DAG Orchestrator Unit Tests

Verifies:
1. Correct parallel batches for a 4-agent manifest
2. Frontend + Backend start simultaneously (no dependencies)
3. CRDT starts after Backend completes
4. QA starts after all three complete
5. Cycle detection raises CycleDetectedError
6. Empty manifest edge case
7. Topological ordering for merge
"""

import pytest
from dag_orchestrator import DagOrchestrator, CycleDetectedError, TaskNotFoundError


# ─── Test Fixtures ────────────────────────────────────────

FOUR_AGENT_MANIFEST = [
    {
        "task_id": "frontend",
        "description": "Build React + CodeMirror 6 frontend with Yjs provider",
        "agent": "frontend-agent",
        "branch": "agent/frontend",
        "depends_on": []
    },
    {
        "task_id": "backend",
        "description": "Build FastAPI + WebSocket backend with Redis pub/sub and JWT auth",
        "agent": "backend-agent",
        "branch": "agent/backend",
        "depends_on": []
    },
    {
        "task_id": "crdt",
        "description": "Build Yjs CRDT sync layer with WebSocket provider",
        "agent": "crdt-agent",
        "branch": "agent/crdt",
        "depends_on": ["backend"]
    },
    {
        "task_id": "qa",
        "description": "Build Playwright E2E tests and integration tests",
        "agent": "qa-agent",
        "branch": "agent/qa",
        "depends_on": ["frontend", "backend", "crdt"]
    }
]

CYCLIC_MANIFEST = [
    {"task_id": "a", "description": "A", "agent": "a", "branch": "a", "depends_on": ["c"]},
    {"task_id": "b", "description": "B", "agent": "b", "branch": "b", "depends_on": ["a"]},
    {"task_id": "c", "description": "C", "agent": "c", "branch": "c", "depends_on": ["b"]},
]


# ─── Test: Parallel Batches ───────────────────────────────

class TestParallelBatches:
    """Verify correct parallel scheduling for the 4-agent manifest."""

    def test_batch_1_frontend_and_backend_start_simultaneously(self):
        """Frontend and Backend have no dependencies → both ready immediately."""
        dag = DagOrchestrator(FOUR_AGENT_MANIFEST)
        ready = dag.get_ready_tasks()
        ready_ids = sorted([t["task_id"] for t in ready])
        assert ready_ids == ["backend", "frontend"], \
            f"Batch 1 should be [backend, frontend], got {ready_ids}"

    def test_batch_2_crdt_after_backend(self):
        """CRDT depends on Backend → unlocks after Backend completes."""
        dag = DagOrchestrator(FOUR_AGENT_MANIFEST)

        # Start and complete Frontend + Backend
        dag.mark_running("frontend")
        dag.mark_running("backend")
        dag.mark_complete("frontend")
        newly_unlocked = dag.mark_complete("backend")

        # CRDT should now be ready
        unlocked_ids = [t["task_id"] for t in newly_unlocked]
        assert "crdt" in unlocked_ids, "CRDT should unlock after Backend completes"

        ready = dag.get_ready_tasks()
        ready_ids = [t["task_id"] for t in ready]
        assert "crdt" in ready_ids
        assert "qa" not in ready_ids, "QA should NOT be ready yet"

    def test_batch_3_qa_starts_last(self):
        """QA depends on all three → only ready after frontend + backend + crdt."""
        dag = DagOrchestrator(FOUR_AGENT_MANIFEST)

        # Complete frontend, backend, crdt in sequence
        dag.mark_running("frontend")
        dag.mark_running("backend")
        dag.mark_complete("frontend")
        dag.mark_complete("backend")

        dag.mark_running("crdt")
        newly_unlocked = dag.mark_complete("crdt")

        unlocked_ids = [t["task_id"] for t in newly_unlocked]
        assert "qa" in unlocked_ids, "QA should unlock after all three complete"

        ready = dag.get_ready_tasks()
        ready_ids = [t["task_id"] for t in ready]
        assert ready_ids == ["qa"]

    def test_full_pipeline_completes(self):
        """Run through all batches and verify is_done()."""
        dag = DagOrchestrator(FOUR_AGENT_MANIFEST)

        # Batch 1
        dag.mark_running("frontend")
        dag.mark_running("backend")
        dag.mark_complete("frontend")
        dag.mark_complete("backend")

        assert not dag.is_done()

        # Batch 2
        dag.mark_running("crdt")
        dag.mark_complete("crdt")

        assert not dag.is_done()

        # Batch 3
        dag.mark_running("qa")
        dag.mark_complete("qa")

        assert dag.is_done(), "All tasks should be complete"


# ─── Test: Cycle Detection ────────────────────────────────

class TestCycleDetection:
    """Verify that cyclic dependencies are detected and rejected."""

    def test_cycle_raises_error(self):
        """A → B → C → A should raise CycleDetectedError."""
        with pytest.raises(CycleDetectedError) as exc_info:
            DagOrchestrator(CYCLIC_MANIFEST)
        assert "cycle" in str(exc_info.value).lower()

    def test_self_dependency_raises_error(self):
        """A task depending on itself should raise an error."""
        self_dep = [
            {"task_id": "x", "description": "X", "agent": "x", "branch": "x", "depends_on": ["x"]}
        ]
        with pytest.raises(CycleDetectedError):
            DagOrchestrator(self_dep)


# ─── Test: Edge Cases ─────────────────────────────────────

class TestEdgeCases:

    def test_empty_manifest(self):
        """Empty manifest should create a valid (trivially done) orchestrator."""
        dag = DagOrchestrator([])
        assert dag.is_done()
        assert dag.get_ready_tasks() == []

    def test_single_task(self):
        """Single task with no dependencies should be immediately ready."""
        dag = DagOrchestrator([
            {"task_id": "solo", "description": "Solo task", "agent": "a", "branch": "b", "depends_on": []}
        ])
        ready = dag.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0]["task_id"] == "solo"

    def test_unknown_dependency_raises_error(self):
        """Depending on a non-existent task should raise TaskNotFoundError."""
        bad_manifest = [
            {"task_id": "a", "description": "A", "agent": "a", "branch": "a", "depends_on": ["nonexistent"]}
        ]
        with pytest.raises(TaskNotFoundError):
            DagOrchestrator(bad_manifest)

    def test_mark_complete_unknown_task_raises(self):
        """Completing a non-existent task should raise TaskNotFoundError."""
        dag = DagOrchestrator(FOUR_AGENT_MANIFEST)
        with pytest.raises(TaskNotFoundError):
            dag.mark_complete("nonexistent")


# ─── Test: Topological Order ──────────────────────────────

class TestTopologicalOrder:

    def test_topological_order_valid(self):
        """Topological order should have each task after all its dependencies."""
        dag = DagOrchestrator(FOUR_AGENT_MANIFEST)
        order = dag.get_topological_order()

        assert len(order) == 4
        # Backend must come before CRDT
        assert order.index("backend") < order.index("crdt")
        # Frontend, Backend, CRDT must all come before QA
        assert order.index("frontend") < order.index("qa")
        assert order.index("backend") < order.index("qa")
        assert order.index("crdt") < order.index("qa")


# ─── Test: Status Reporting ───────────────────────────────

class TestStatusReporting:

    def test_initial_status_all_pending(self):
        dag = DagOrchestrator(FOUR_AGENT_MANIFEST)
        status = dag.get_status()
        for tid, info in status.items():
            assert info["state"] == "PENDING"

    def test_status_reflects_running(self):
        dag = DagOrchestrator(FOUR_AGENT_MANIFEST)
        dag.mark_running("frontend")
        status = dag.get_status()
        assert status["frontend"]["state"] == "RUNNING"
        assert status["backend"]["state"] == "PENDING"

    def test_status_reflects_complete(self):
        dag = DagOrchestrator(FOUR_AGENT_MANIFEST)
        dag.mark_running("frontend")
        dag.mark_complete("frontend")
        status = dag.get_status()
        assert status["frontend"]["state"] == "COMPLETE"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
