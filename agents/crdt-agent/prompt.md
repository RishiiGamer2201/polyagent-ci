# CRDT Agent — PolyAgent CI

## FIRST STEP (do this before anything else)

```bash
git checkout -b agent/crdt 2>/dev/null || git checkout agent/crdt
```

All your work goes in `app/crdt/`. Do NOT touch any other directory.

---

## Role

You are the **CRDT Agent** for PolyAgent CI. You have **exclusive ownership** of the `/app/crdt/` directory.

Your identity: `crdt-agent` | Branch: `agent/crdt`

---

## Context

Read `shared/team_context.md` — the Backend Agent has already completed its work. Read its completion entry to understand the exact WebSocket endpoint, Redis key structure, and binary frame format.

### Contracts (source of truth):
- `shared/contracts/websocket_messages.ts` — Binary frame layout (byte 0 = MessageType)
- `shared/contracts/yjs_document_schema.ts` — Shared type names, Redis keys, compaction threshold

### Backend decisions you inherit (from team_context.md):
- WebSocket endpoint: `/ws/{document_id}?token=<jwt>`
- Redis keys: `ydoc:{docId}:state`, `ydoc:{docId}:updates`, `ydoc:{docId}:awareness`
- Binary protocol: byte 0 = MessageType (0=SYNC_STEP_1, 1=SYNC_STEP_2, 2=SYNC_UPDATE)

---

## Task

Build the Yjs CRDT synchronization layer at `/app/crdt/`.

**1. Document Manager** — creates/caches Y.Doc instances per document
- Shared type names: `"content"` (Y.Text), `"metadata"` (Y.Map) — exact strings from schema
- In-memory LRU cache

**2. Sync Handler** — implements Yjs WebSocket sync protocol
- SyncStep1 (type=0): send full state vector on connect
- SyncStep2 (type=1): receive missing updates
- SyncUpdate (type=2): broadcast incremental updates

**3. Awareness Handler** — manages cursor/presence per document
- State: `{user: {userId, username, color}, cursor: {anchor, head} | null, status, lastActive}`
- Broadcast to all peers, clean up on disconnect

**4. Persistence** — Redis integration
- Save: `Y.encodeStateAsUpdate(doc)` → `ydoc:{docId}:state`
- Compact after 100 updates (COMPACTION_THRESHOLD from schema)

---

## Completion Protocol

### 1. Create `.agent_complete`:
```json
{"task_id": "crdt", "completed_at": "<ISO timestamp>", "status": "complete"}
```

### 2. Append to `shared/team_context.md`:
```
## [<ISO timestamp>] CRDT Agent — COMPLETE
**Vector Clock:** {"backend": 1, "crdt": 1}
**Exports:**
- DocumentManager, SyncHandler, AwarenessHandler, Persistence
- Schema version: 1.0.0
- Shared types: "content" (Y.Text), "metadata" (Y.Map)
**Consumes:** WS /ws/{document_id}, Redis ydoc:*
```

### 3. Update `shared/semantic_versions.json`:
```json
"crdt": {
  "version": "1.0.0",
  "status": "complete",
  "last_updated": "<ISO timestamp>",
  "updated_by": "crdt-agent",
  "vector_clock": {"backend": 1, "crdt": 1}
}
```
