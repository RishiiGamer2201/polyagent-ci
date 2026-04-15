# PolyAgent CI

> **Multi-Agent Orchestration Platform** — 4 specialized AI agents build a real application simultaneously on isolated git branches, coordinated by a DAG-based Python orchestrator.

![Status](https://img.shields.io/badge/status-hackathon_demo-blue)
![Python](https://img.shields.io/badge/python-3.11+-green)
![Agents](https://img.shields.io/badge/agents-4_parallel-purple)

---

## 🏗️ Architecture

```
                    ┌─────────────────────────────────────┐
                    │         PolyAgent CI Orchestrator    │
                    │  ┌──────────┐  ┌─────────────────┐  │
                    │  │ Manifest │→ │ DAG Orchestrator │  │
                    │  │Generator │  │ (Kahn's algo)    │  │
                    │  └──────────┘  └────────┬────────┘  │
                    │                         │           │
                    │  ┌──────────────────────┼───────┐   │
                    │  │    Agent Runner       │       │   │
                    │  │  (parallel dispatch)  │       │   │
                    │  └──────────────────────┼───────┘   │
                    └─────────────────────────┼───────────┘
                              ┌───────────────┼───────────────┐
                              │               │               │
                    ┌─────────▼──┐  ┌────────▼───┐  ┌───────▼─────┐
                    │  Frontend  │  │  Backend   │  │    CRDT     │
                    │   Agent    │  │   Agent    │  │    Agent    │
                    │ React+CM6  │  │ FastAPI+WS │  │  Yjs Sync   │
                    └────────────┘  └─────┬──────┘  └──────┬──────┘
                              │           │               │
                              └───────────┼───────────────┘
                                          │
                              ┌───────────▼───────────┐
                              │      QA Agent         │
                              │   Playwright E2E      │
                              └───────────┬───────────┘
                                          │
                    ┌─────────────────────┼───────────────┐
                    │  Review Agent → Conflict Resolver   │
                    │  Merge Coordinator (topological)    │
                    └─────────────────────────────────────┘
```

## 🎯 What It Does

1. **Contract-First**: Three contract files define the entire API surface before any code is written
2. **Parallel Build**: 4 agents work simultaneously on isolated git worktrees
3. **DAG Scheduling**: Tasks are ordered by dependencies using Kahn's algorithm
4. **Semantic Review**: AI reviews diffs against contracts for semantic conflicts
5. **Auto-Resolution**: Critical conflicts get dual-option analysis with automatic lower-risk fix
6. **Topological Merge**: Branches merge in dependency order with test gates
7. **Live Dashboard**: Rich terminal UI showing agent states, DAG progress, and event log

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Git
- DevSwarm (for real agent sessions)

### Setup

```powershell
cd polyagent-ci

# Install dependencies
pip install -r requirements.txt

# Configure API keys (already in .env)
# GEMINI_API_KEY, GROQ_API_KEY, MISTRAL_API_KEY
```

### Run the Demo

```powershell
# 1. Generate task manifest (offline mode)
python generate_manifest.py --offline

# 2. Run DAG orchestrator tests
python -m pytest test_dag_orchestrator.py -v

# 3. Launch the dashboard (animated demo)
python dashboard.py --demo-mode

# 4. Review agent demo (shows seeded conflict)
python review_agent.py --task-id frontend --demo-mode

# 5. Conflict resolution demo
python conflict_resolver.py --demo-mode

# 6. Speculative scheduler demo
python speculative_scheduler.py --demo-mode

# 7. Merge coordinator demo
python merge_coordinator.py --manifest manifests/manifest_*_offline.json --demo-mode
```

### Full Pipeline (with DevSwarm)

```powershell
# 1. Generate manifest
python generate_manifest.py --provider gemini

# 2. Set up worktrees
.\setup_branches.ps1 -ManifestPath (Get-ChildItem manifests\*.json | Select -Last 1)

# 3. Launch agents + dashboard (in parallel terminals)
python run_agents.py --manifest manifests/manifest_*.json    # Terminal 1
python dashboard.py                                           # Terminal 2

# 4. After agents complete, run review
python review_agent.py --review-all

# 5. Resolve conflicts
python conflict_resolver.py

# 6. Merge branches
python merge_coordinator.py --manifest manifests/manifest_*.json
```

---

## 📁 Project Structure

```
polyagent-ci/
├── shared/
│   ├── contracts/
│   │   ├── openapi_spec.yaml        ← REST API (source of truth)
│   │   ├── websocket_messages.ts     ← WebSocket messages (source of truth)
│   │   └── yjs_document_schema.ts    ← CRDT structure (source of truth)
│   ├── team_context.md               ← Inter-agent communication
│   └── semantic_versions.json        ← Version tracking
├── prompts/
│   ├── frontend_prompt.md            ← Frontend agent instructions
│   ├── backend_prompt.md             ← Backend agent instructions
│   ├── crdt_prompt.md                ← CRDT agent instructions
│   └── qa_prompt.md                  ← QA agent instructions
├── generate_manifest.py              ← AI-powered task manifest generation
├── dag_orchestrator.py               ← Kahn's algorithm DAG scheduler
├── test_dag_orchestrator.py          ← 14 unit tests (all passing ✅)
├── setup_branches.ps1                ← Git worktree creation
├── run_agents.py                     ← Parallel agent launcher
├── review_agent.py                   ← Semantic conflict detector
├── conflict_resolver.py              ← Dual-option conflict resolution
├── merge_coordinator.py              ← Topological merge + test gates
├── speculative_scheduler.py          ← Speculative execution engine
├── dashboard.py                      ← Rich terminal dashboard 🎨
└── requirements.txt                  ← Python dependencies
```

---

## 🤖 Agents

| Agent | Directory | Dependencies | Role |
|-------|-----------|-------------|------|
| Frontend | `/app/frontend/` | None | React + CodeMirror 6, Yjs binding, awareness UI |
| Backend | `/app/backend/` | None | FastAPI, WebSocket, Redis, JWT auth |
| CRDT | `/app/crdt/` | Backend | Yjs sync protocol, persistence, awareness |
| QA | `/app/tests/` | All | Playwright E2E, integration, convergence tests |

### Communication Rules
- Agents communicate **ONLY** through `team_context.md` and `semantic_versions.json`
- Each agent owns exactly **ONE** directory
- Contract changes require the **Contract Change Protocol**

---

## 🏗️ The Application Being Built

A **real-time collaborative Markdown editor**:

- **Frontend**: React 18 + CodeMirror 6 + TypeScript
- **Backend**: FastAPI + WebSockets + Redis pub/sub + JWT auth
- **CRDT**: Yjs (conflict-free replicated data type)
- **Tests**: Playwright end-to-end tests

**Demo shows**: Type in one browser window → text appears in another in **under 200ms**.

---

## 📊 Demo Scenario

1. ▶️ **4 agents start** — Frontend + Backend in parallel, CRDT waits for Backend, QA waits for all
2. 🔍 **Review Agent** catches a seeded conflict: Frontend uses `/api/docs` instead of `/documents`
3. 🔧 **Conflict Resolver** presents two options, auto-applies the lower-risk fix
4. 🔀 **Merge Coordinator** merges branches in topological order: Backend → CRDT → Frontend → QA
5. ✅ **All tests pass** on the fully integrated codebase
6. 🖥️ **Live demo** — two browser windows, real-time collaborative editing

---

## 📋 Key Design Decisions

- **Gemini AI** (primary) + Groq/Mistral (fallback) for manifest generation and code review
- **Kahn's algorithm** for topological scheduling with O(V+E) complexity
- **DFS cycle detection** prevents invalid dependency graphs
- **Sentinel files** (`.agent_complete`) for completion signaling
- **Binary + JSON** WebSocket frames for efficient Yjs sync
- **Redis** for cross-process pub/sub and document persistence

---

## 🧪 Testing

```powershell
# Run DAG orchestrator tests
python -m pytest test_dag_orchestrator.py -v

# Expected: 14 passed ✅
```

---

*Built for hackathon demo by PolyAgent CI team.*