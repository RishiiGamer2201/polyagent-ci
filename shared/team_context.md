# PolyAgent CI — Team Context

> **This file is the shared communication channel between agents.**
> Agents communicate ONLY through this file and `semantic_versions.json`.
> Direct agent-to-agent communication is forbidden.

---

## Project Overview

**Project:** Real-time Collaborative Markdown Editor
**Architecture:** React + CodeMirror 6 | FastAPI + WebSockets | Yjs CRDT | Playwright Tests
**Orchestrator:** PolyAgent CI (DAG-based parallel agent coordination)

---

## Agent Assignments

| Agent | Directory | Responsibility |
|-------|-----------|---------------|
| `frontend-agent` | `/app/frontend/` | React UI, CodeMirror 6, Yjs binding, awareness cursors |
| `backend-agent` | `/app/backend/` | FastAPI, WebSocket, Redis pub/sub, JWT auth, document CRUD |
| `crdt-agent` | `/app/crdt/` | Yjs document manager, sync protocol, persistence, awareness |
| `qa-agent` | `/app/tests/` | Playwright E2E tests, integration tests, convergence tests |

**Rule:** Each agent owns exactly ONE directory and must NEVER modify files outside it.

---

## Shared Contracts (Source of Truth)

1. `shared/contracts/openapi_spec.yaml` — All HTTP endpoints (REST API)
2. `shared/contracts/websocket_messages.ts` — WebSocket message shapes & protocol
3. `shared/contracts/yjs_document_schema.ts` — CRDT document structure & schema

**Contract Change Protocol:**
1. Propose change in this file (team_context.md)
2. Check which agents have consumed the contract
3. Issue targeted reconciliation prompts to affected agents
4. Only then update the contract file

---

## Architecture Decisions

- **Auth:** JWT Bearer tokens (see openapi_spec.yaml `BearerAuth` scheme)
- **WebSocket URL:** `/ws/{document_id}?token=<jwt>`
- **Document sync:** Yjs binary sync protocol (SyncStep1 → SyncStep2 → SyncUpdate)
- **Awareness:** Yjs awareness protocol for cursor sharing (separate from doc state)
- **Persistence:** Redis — `ydoc:{docId}:state` (binary), `ydoc:{docId}:updates` (list)
- **Compaction:** After 100 incremental updates, merge into full state

---

## Completion Log

> Agents append their completion entries here when done.

<!-- COMPLETION_LOG_START -->
<!-- COMPLETION_LOG_END -->

---

## Proposed Changes

> Agents propose contract changes here before modifying contract files.

<!-- PROPOSED_CHANGES_START -->
<!-- PROPOSED_CHANGES_END -->
