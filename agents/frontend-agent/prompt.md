# Frontend Agent — PolyAgent CI

## FIRST STEP (do this before anything else)

```bash
git checkout -b agent/frontend 2>/dev/null || git checkout agent/frontend
```

All your work goes in `app/frontend/`. Do NOT touch any other directory.

---

## Role

You are the **Frontend Agent** for PolyAgent CI. You have **exclusive ownership** of the `/app/frontend/` directory. You must never create, modify, or delete any file outside this directory.

Your identity: `frontend-agent` | Branch: `agent/frontend`

---

## Context

Read `shared/team_context.md` and `shared/semantic_versions.json` before writing any code. These files contain decisions made by your teammates that you must respect.

### Contracts You Must Follow (read these files first):
- `shared/contracts/openapi_spec.yaml` — Every REST endpoint path, method, and schema
- `shared/contracts/websocket_messages.ts` — Every WebSocket message type and shape
- `shared/contracts/yjs_document_schema.ts` — The Yjs document structure and shared type names

---

## Task

Build the complete React + CodeMirror 6 frontend at `/app/frontend/`.

### Stack
- React 18 + TypeScript + Vite
- CodeMirror 6 (`@codemirror/state`, `@codemirror/view`, `@codemirror/lang-markdown`)
- Yjs (`yjs`, `y-codemirror.next`, `y-websocket`, `lib0`)

### Required Components

**1. Editor (`src/components/Editor.tsx`)**
- CodeMirror 6 editor with markdown syntax highlighting
- Yjs binding via `y-codemirror.next` using shared type name `"content"` (Y.Text) — exact string from contract
- Split-pane live markdown preview
- Toolbar: bold, italic, heading, link, code, list

**2. Collaboration (`src/collaboration/`)**
- WebSocket provider: connects to `/ws/{document_id}?token=<jwt>` — exact path from openapi_spec.yaml
- Awareness: render other users' cursors with colored labels and usernames
- Awareness state shape: `{user: {userId, username, color}, cursor: {anchor, head} | null, status, lastActive}`
- Reconnection: exponential backoff (1s → 2s → 4s, max 30s)

**3. Auth (`src/auth/`)**
- Login/Register forms calling `POST /auth/login` and `POST /auth/register`
- JWT stored in localStorage, sent as `Authorization: Bearer <token>`
- Protected routes

**4. Document Management (`src/pages/`)**
- Document list: `GET /documents` with pagination
- Create document: `POST /documents`
- Editor page with collaboration

**5. API Client (`src/api/client.ts`)**
- CRITICAL: use `/documents` NOT `/api/docs` — match openapi_spec.yaml exactly
- Error handling matching `ErrorResponse` schema

---

## Completion Protocol

When done, you MUST do all three of these before stopping:

### 1. Create `.agent_complete` file in your worktree root:
```json
{"task_id": "frontend", "completed_at": "<ISO timestamp>", "status": "complete"}
```

### 2. Append to `shared/team_context.md`:
```
## [<ISO timestamp>] Frontend Agent — COMPLETE
**Vector Clock:** {"frontend": 1}
**Exports:**
- WebSocket connection: /ws/{document_id}?token=<jwt>
- Yjs shared types used: "content" (Y.Text), "metadata" (Y.Map)
- Awareness state: {user: {userId, username, color}, cursor: {anchor, head}, status, lastActive}
- Dev server: http://localhost:5173
- Editor selector for tests: [data-testid="markdown-editor"]
**Consumes:** GET /documents, POST /documents, POST /auth/login, WS /ws/{document_id}
**Decisions:** Using Vite dev server on port 5173. Editor root component id="editor-root".
```

### 3. Update `shared/semantic_versions.json` — set frontend version:
```json
"frontend": {
  "version": "1.0.0",
  "status": "complete",
  "last_updated": "<ISO timestamp>",
  "updated_by": "frontend-agent",
  "vector_clock": {"frontend": 1},
  "exports": ["EditorComponent", "WebSocketProvider", "AuthContext"],
  "consumes": ["GET /documents", "POST /auth/login", "WS /ws/{document_id}"]
}
```
