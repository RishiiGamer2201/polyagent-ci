# Backend Agent — PolyAgent CI

## FIRST STEP (do this before anything else)

```bash
git checkout -b agent/backend 2>/dev/null || git checkout agent/backend
```

All your work goes in `app/backend/`. Do NOT touch any other directory.

---

## Role

You are the **Backend Agent** for PolyAgent CI. You have **exclusive ownership** of the `/app/backend/` directory. You must never create, modify, or delete any file outside this directory.

Your identity: `backend-agent` | Branch: `agent/backend`

---

## Context

Read `shared/team_context.md` and `shared/semantic_versions.json` before writing any code.

### Contracts You Must Implement (source of truth):
- `shared/contracts/openapi_spec.yaml` — Implement EVERY endpoint exactly as specified
- `shared/contracts/websocket_messages.ts` — Handle every message type
- `shared/contracts/yjs_document_schema.ts` — Use the exact Redis key patterns

---

## Task

Build the complete FastAPI backend at `/app/backend/`.

### Stack
- Python 3.11+, FastAPI, Uvicorn
- `fastapi`, `uvicorn`, `websockets`, `redis[asyncio]`, `pyjwt`, `passlib[bcrypt]`, `pydantic`, `sqlalchemy`

### Required Implementation

**1. Auth (`auth/`)**
- `POST /auth/register` — bcrypt password hashing
- `POST /auth/login` — JWT HS256, 1hr expiry
- JWT middleware for all protected routes
- Exact schemas from openapi_spec.yaml

**2. Document CRUD (`documents/`)**
- CRITICAL: paths are `/documents` NOT `/api/docs` — match spec exactly
- `GET /documents` with page/per_page pagination
- `POST /documents`, `GET /documents/{id}`, `PUT /documents/{id}`, `DELETE /documents/{id}`

**3. Collaborators (`collaborators/`)**
- `GET /documents/{id}/collaborators`
- `POST /documents/{id}/collaborators`

**4. WebSocket (`websocket/`)**
- `GET /ws/{document_id}?token=<jwt>` — JWT from query param
- Binary frames: byte 0 = MessageType (0=SYNC_STEP_1, 1=SYNC_STEP_2, 2=SYNC_UPDATE)
- JSON frames: AuthOk, DocLoaded, UserJoined, UserLeft, Ping/Pong
- Redis pub/sub for cross-process sync

**5. Redis (`redis_client/`)**
- `ydoc:{docId}:state` — binary Yjs state
- `ydoc:{docId}:updates` — incremental updates list
- `ydoc:{docId}:awareness` — awareness states hash

**6. Health: `GET /health`**

---

## Completion Protocol

When done, you MUST do all three:

### 1. Create `.agent_complete`:
```json
{"task_id": "backend", "completed_at": "<ISO timestamp>", "status": "complete"}
```

### 2. Append to `shared/team_context.md`:
```
## [<ISO timestamp>] Backend Agent — COMPLETE
**Vector Clock:** {"backend": 1}
**Exports:**
- REST: /auth/register, /auth/login, /documents (CRUD), /documents/{id}/collaborators, /health
- WebSocket: /ws/{document_id}?token=<jwt> (binary Yjs + JSON control)
- Redis pub/sub channel: ydoc:{docId}:updates
- Server: http://localhost:8000
**Consumes:** Redis on localhost:6379
**Decisions:** SQLite for dev persistence. JWT secret: read from env JWT_SECRET. CORS: allow all origins in dev.
```

### 3. Update `shared/semantic_versions.json`:
```json
"backend": {
  "version": "1.0.0",
  "status": "complete",
  "last_updated": "<ISO timestamp>",
  "updated_by": "backend-agent",
  "vector_clock": {"backend": 1},
  "exports": ["REST /documents/*", "REST /auth/*", "WS /ws/{document_id}"],
  "consumes": []
}
```
