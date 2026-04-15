# POLYAGENT CI
## Complete Technical Implementation Plan
**DevSwarm Hackathon — Orchestrate the Swarm**

---

### The Core Idea in One Sentence

Every AI coding tool today forces one human and one AI to work together on one task at a time. PolyAgent CI breaks that bottleneck by running four specialized AI agents simultaneously on separate parts of the same codebase — coordinated by an intelligent orchestration system borrowed from CPU architecture and distributed database theory.

---

## Part 1 — The Problem We Are Solving

Before we talk about what we are building, it helps to understand exactly what is broken about how AI coding tools work today.

### 1.1 The Single-Thread Bottleneck

Tools like GitHub Copilot, Cursor, and Antigravity all share the same mental model: one human sits in one editor, and the AI whispers suggestions into that human's ear. The human is still doing all the thinking — the AI just helps them type faster.

The problem is that the human is the bottleneck. Everything moves at human speed. When the developer stops, everything stops. When they switch from working on the frontend to the backend, they lose context. The AI loses context with them. This is like having a supercomputer that can only use one of its thousands of cores at a time — the hardware is capable of so much more than the architecture allows.

### 1.2 What a Real Engineering Team Looks Like

Now think about how a real software company works. There is a frontend team, a backend team, a QA team, and a tech lead who coordinates all of them. These people work simultaneously. The tech lead does not write every line of code — they decompose the problem, assign ownership, manage dependencies, review pull requests, and integrate everything at the end.

PolyAgent CI is that entire company structure, running as AI agents. The agents work in parallel on isolated git branches. An orchestration system acts as the tech lead — tracking dependencies, detecting conflicts, and coordinating merges. The result is not just faster code generation — it is a fundamentally different architecture for how AI builds software.

### The Hackathon Framing

The judging criteria rewards parallelization (30%), creative use of DevSwarm (25%), final product quality (25%), and documentation (20%). PolyAgent CI is designed to score at the top of every single category because it doesn't just use DevSwarm — it uses DevSwarm to build a system that demonstrates every advanced concept in distributed software development.

---

## Part 2 — High-Level Architecture

The system has five layers that work together. Think of them as the organs of a body — each one has a specific job, and together they produce something none could produce alone.

### 2.1 The Five Layers at a Glance

| Layer | What It Does |
|---|---|
| 1. Task Ingestion | Converts a plain-English project description into a machine-readable plan with formal dependencies. |
| 2. DAG Orchestrator | Reads the plan, figures out which tasks can run at the same time, and schedules agents accordingly. |
| 3. Parallel Agents | Four specialized AI agents that each own one part of the codebase and work simultaneously. |
| 4. Review Agent | Automatically reads each agent's completed work and checks for conflicts before merging. |
| 5. Merge Coordinator | Merges completed branches in the correct order, runs tests, and handles failures automatically. |

On top of all of this sits an **Observability Dashboard** — a live terminal view that shows every agent's current state, the dependency graph, and a running log of everything happening. This is what judges will see during the demo.

### 2.2 The Application Being Built

The agents are not building the orchestration system itself — they are building a real application that demonstrates the system works. That application is a **real-time collaborative Markdown editor** with the following components:

- A **React frontend** with a CodeMirror 6 editor (the same engine used by Replit and Obsidian), a live Markdown preview panel, and colored cursors showing which user is editing where.
- A **FastAPI backend** with WebSocket support, JWT authentication, Redis for broadcasting changes to all connected clients, and SQLite for document persistence.
- A **Yjs CRDT layer** that handles the hard problem of simultaneous editing — when two users type at the same time, Yjs merges their changes mathematically so there is no conflict. This is the same technology that powers Google Docs, Notion, and Linear.
- A **test suite** covering every API endpoint, the WebSocket flow, and an end-to-end Playwright test that opens two browser windows and verifies that typing in one appears in the other within 200 milliseconds.

---

## Part 3 — The Contract-First Phase (Before Any Agent Writes Code)

This is one of the most important innovations in the design. Most parallel development fails because each team member makes different assumptions about how the pieces will fit together. You discover the mismatch at integration time — when it is most expensive to fix.

PolyAgent CI solves this by forcing agreement on interfaces before any implementation begins. Think of it like how a construction project works: before anyone lays bricks, the architect produces blueprints that every contractor must follow. Our blueprints are called **contracts**.

### 3.1 What Gets Defined in the Contract-First Phase

Before the agents start, the Orchestrator generates three formal contract documents and commits them to the `/shared/contracts/` directory:

**The OpenAPI Specification**
This is a machine-readable document that defines every HTTP endpoint in the backend API — what URL each endpoint lives at, what parameters it accepts, what it returns, and what errors it can produce. Importantly, this is the definitive list of endpoint names. This is how we prevent the exact kind of bug described in the design notes — where Agent 1 calls `/api/document/update` but Agent 2 built `/api/docs/patch`.

**The WebSocket Message Format**
A TypeScript interface definition that specifies the exact structure of every message that can be sent over the WebSocket connection. Every field, every type, every optional property is defined here. Agent 2 (backend) builds to this spec. Agent 1 (frontend) builds to this spec. They never need to coordinate directly — the contract is the coordination.

**The Yjs Document Schema**
A formal description of the Yjs shared data structure — what properties the collaborative document has, how the CRDT state maps to the visible document content, and how the presence information (user cursors) is represented. Agent 3 (CRDT) and Agent 1 (frontend) both build against this schema.

### 3.2 The Contract Change Protocol

Contracts can change — requirements evolve. But changing a contract mid-build is dangerous if another agent has already built against the old version. The protocol handles this carefully:

1. An agent that needs to change a contract writes a formal **contract change proposal** to the shared context, not to the contract file directly.
2. The Orchestrator reads the proposal and checks the Semantic Version Manifest to see which other agents have already consumed the current version of that contract.
3. If an agent has already built against the old version, the Orchestrator generates a targeted **reconciliation prompt** for that agent — telling it specifically which files need updating and what changed.
4. Only after reconciliation is complete does the Orchestrator update the contract file and increment the version number.

> **WHY THIS MATTERS:** This is how real distributed API teams work. You version your APIs and you don't break consumers without warning. We are applying this discipline to AI agent coordination.

---

## Part 4 — Task Manifest Generation

Once contracts are in place, the first real step is turning the project description from English into a machine-readable plan. This is what the `generate_manifest.py` script does.

### 4.1 What the Task Manifest Contains

The Orchestrator calls the Claude API with the project description and asks it to produce a structured JSON document. Every task in that document contains:

- A unique **ID** that other tasks can reference.
- A human-readable **name** and detailed **description** of what this task involves.
- The name of the **git branch** where this work will happen.
- The **agent** that will be assigned to this task.
- A list of other task IDs that must be complete before this task can begin. This is the `depends_on` field, and it is what makes formal scheduling possible.

### 4.2 Cycle Detection — Making Sure the Plan Makes Sense

After generating the manifest, the system does something important: it validates that the dependency graph contains no cycles. A cycle would mean Task A depends on Task B, and Task B depends on Task A — a deadlock where neither can ever start.

The validation runs a depth-first search topological sort on the graph. If a cycle is detected, the system asks Claude to revise the manifest rather than proceeding with a broken plan. This happens before any agent is launched, which means we catch planning errors at the cheapest possible moment.

---

## Part 5 — The DAG Orchestrator

DAG stands for **Directed Acyclic Graph**. It is a map of tasks where arrows represent dependencies. The Orchestrator is the brain of the entire system — it reads the Task Manifest and turns it into a real execution schedule.

### 5.1 How Topological Sorting Works (Simply Explained)

Imagine you are cooking a meal. You cannot serve food before you cook it. You cannot cook it before you chop the vegetables. You cannot chop the vegetables before you buy them. These are your dependencies. Topological sort figures out the correct order to do everything such that you never try to do something before its prerequisites are done.

For our system, the algorithm is **Kahn's algorithm**. It works like this: start with all tasks that have zero dependencies. Those can run right now. As each task finishes, remove it from the dependency lists of everything that was waiting on it. Any task whose dependency list is now empty joins the pool of tasks that can run. Repeat until everything is done.

### 5.2 The `get_ready_tasks()` Method

The `DagOrchestrator` class exposes a method called `get_ready_tasks()` that the rest of the system calls to find out what work can be started right now. It returns the current set of tasks with no unresolved dependencies. This is the set that gets dispatched to DevSwarm for parallel execution.

### 5.3 The `mark_complete()` Method

When an agent finishes its work, the system calls `mark_complete(task_id)`. This removes the completed task from the dependency lists of everything waiting on it, then recomputes the ready set. If any tasks just had their last dependency resolved, they immediately join the ready pool and the Orchestrator launches new agents for them.

**The Parallelism This Enables**

In our specific project: Agent 1 (frontend) and Agent 2 (backend) can start simultaneously because they only share the contracts, not actual code. Agent 3 (CRDT) waits for Agent 2 to complete certain interface decisions. Agent 4 (tests) starts immediately writing contract tests and then writes integration tests as the other agents finish.

---

## Part 6 — Shared Context and Semantic Versioning

This is the mechanism that allows agents to be aware of each other's decisions without talking directly to each other. Think of it as a shared whiteboard that every agent can read and write to.

### 6.1 The Team Context Document

Before any agent starts, a file called `team_context.md` is initialized as empty in the `/shared/` directory. As agents make architectural decisions, they write those decisions to this file.

For example: when Agent 2 decides on the exact format of the WebSocket authentication handshake, it writes that decision to the team context document with a timestamp. When Agent 1 reads this document before implementing the frontend WebSocket client, it sees that decision and builds accordingly. The agents are not telepathic — they communicate through this shared document.

### 6.2 The Semantic Version Manifest

The `semantic_versions.json` file tracks the current version of every major interface in the system. It has entries for things like `api_schema_version`, `websocket_message_format_version`, `crdt_document_model_version`, and `auth_token_format_version`.

Every time an agent changes an interface — even slightly — it increments the relevant version number and records what changed. This creates an audit trail and enables the fast-path conflict detection described in the next section.

### 6.3 Vector Clock Timestamps for Causal Consistency

Here is a subtle but important problem: suppose Agent 3 reads a decision that Agent 2 made, and builds on it. Then Agent 4 reads Agent 3's output but misses the original decision Agent 2 made. Agent 4 now has an incomplete picture.

We prevent this with **vector clock timestamps**. Every entry in the team context document gets a version stamp that records not just when it was written, but which other entries it depended on. When Agent 4 reads Agent 3's output, the system automatically traces Agent 3's dependencies and makes sure Agent 4 also has access to those earlier decisions. This is called **causal consistency** — a concept borrowed from distributed databases — and it ensures no agent ever builds on incomplete information.

---

## Part 7 — The Four Parallel Agents

Each agent is given a prompt file that contains four mandatory sections. This structure is not optional — it is what makes the system work reliably.

### 7.1 The Four Prompt Sections (Same for Every Agent)

- **Role:** A precise definition of exactly what this agent owns and what it does not own. Clear ownership prevents agents from accidentally doing each other's work.
- **Context:** The current contents of `team_context.md` and `semantic_versions.json`, embedded verbatim. This is how the agent knows what its teammates have decided.
- **Task:** The specific technical specification for this agent's work, derived from the Task Manifest.
- **Completion Protocol:** Instructions for what the agent must do when it finishes — specifically, writing its semantic version contributions to `semantic_versions.json` and updating `team_context.md` with any decisions it made that other agents should know about.

### 7.2 Agent 1 — The Frontend Agent

This agent owns the React frontend application. It builds a CodeMirror 6 editor instance with split-pane Markdown preview, a WebSocket client that connects to the backend, and a presence system that renders colored cursors for each connected user. It works entirely inside the `frontend` git branch and reads the WebSocket message format contract to know exactly what messages to send and receive.

### 7.3 Agent 2 — The Backend Agent

This agent owns the FastAPI backend. It builds the WebSocket connection manager that handles multiple simultaneous browser connections, a REST API for creating, reading, and updating documents, JWT-based authentication, and a Redis pub/sub layer that broadcasts document changes to all connected clients. It also builds the bridge to the Yjs y-websocket server adapter. When it makes interface decisions that affect other agents, it writes them to the team context document immediately.

### 7.4 Agent 3 — The CRDT Agent

This agent owns the Yjs integration layer. Yjs is a production-grade CRDT (Conflict-free Replicated Data Type) library. The way CRDTs work is genuinely elegant: two users can make edits to a document simultaneously, and the mathematical properties of the data structure guarantee that when those edits are merged, the result is always correct — no server arbitration needed, no "who wins" decision required. Agent 3 integrates Yjs into both the frontend and backend so that all connected clients stay in sync automatically. This is the same technology that powers Google Docs.

### 7.5 Agent 4 — The QA Agent

This agent starts immediately — it does not wait for the others to finish. In the first phase, it writes **contract tests**: tests that validate the OpenAPI spec and WebSocket message format, which fail initially because there is no implementation. As Agent 2 completes endpoints, those tests begin passing, giving the team real-time progress feedback. In the second phase, once all other agents finish, it writes integration tests for the WebSocket flow and Playwright end-to-end tests. It also generates Swagger documentation automatically from the FastAPI route definitions.

### 7.6 Agent Skill Specialization

Not all tasks have the same computational requirements. The Task Manifest tags each task with a **complexity score**. High-complexity tasks — like architecture decisions and CRDT implementation — are given more reasoning budget. Lower-complexity tasks like test scaffolding can be handled with a faster, lighter configuration. The Orchestrator allocates compute budget dynamically based on these complexity scores.

---

## Part 8 — Speculative Execution

This is the concept borrowed from CPU architecture, and it is one of the most intellectually interesting parts of the system.

### 8.1 The CPU Analogy

Modern CPUs do not wait for one instruction to finish before starting the next. Instead, they guess what the result of the current instruction will be and speculatively start executing the next instruction based on that guess. If the guess was correct, they saved time. If the guess was wrong, they roll back the speculative work and redo it with the correct value. The net effect is dramatically higher throughput because idle waiting time is eliminated.

### 8.2 Applied to Agents

In our system, Agent 3 (CRDT) has a dependency on Agent 2 (backend) because it needs to know the WebSocket message format before it can write the synchronization layer. Without speculative execution, Agent 3 would sit idle until Agent 2 finishes — wasted time.

With speculative execution, the `SpeculativeScheduler` generates a best-guess assumption document about what the WebSocket message format will look like, based on the contracts and common patterns. Agent 3 starts building against this assumption immediately. When Agent 2 finishes and the actual message format is known, the system diffs the actual output against the assumption.

If the two are similar enough — above an **80% structural similarity threshold** — Agent 3's speculative work is declared valid and accepted as-is. If they diverge, the system generates a targeted revision prompt that tells Agent 3 specifically which files need updating and what changed. Agent 3 does not restart from scratch — it applies a surgical fix.

### 8.3 Incremental Reconciliation

The key phrase above is "surgical fix." When a dependency changes mid-build, the naive response is to throw away all the speculative work and start over. This wastes enormous time. **Incremental Reconciliation** instead produces a targeted patch prompt: *"Your assumption about the authentication field was correct except for one thing — the field name changed from `token` to `auth_token`. Update only the three files that reference this field."*

This is how human engineering teams actually respond to API changes. You do not rewrite your entire frontend when one field name changes. You update the three files that reference it.

---

## Part 9 — The Review Agent

After each agent pushes its completed branch, the Review Agent wakes up and performs an automated code review before anything is merged. This is not optional — every branch must pass Review before the Merge Coordinator will touch it.

### 9.1 Semantic Conflict Detection

Normal Git conflict detection is syntactic — it compares text and reports when two branches changed the same line. This is completely blind to meaning. It cannot catch the case where Agent 1 is calling `/api/document/update` but Agent 2 named that endpoint `/api/docs/patch`. Those are semantically the same thing with different names, and Git would never flag it.

The Review Agent catches **semantic conflicts** by reading the actual diffs with understanding. It receives the full diff of a branch against main, the current semantic version manifest, and explicit instructions to check for interface mismatches against all previously completed branches.

### 9.2 Version Mismatch Fast-Path

Before reading thousands of lines of code, the Review Agent uses a fast-path: it compares semantic version numbers. If Agent 1 was built against `websocket_message_format_version v2` but Agent 2 has since shipped `v3`, the Review Agent immediately knows there is a compatibility issue without reading a single line of code. It can then focus its detailed analysis exactly on the interfaces that changed between v2 and v3.

### 9.3 The Structured Review Report

The Review Agent's output is always structured JSON with three fields per issue: `task_id` (which agent is responsible), `severity` (critical, warning, or info), and `suggested_fix` (a targeted prompt telling the responsible agent exactly what to change and why). This structured format is what allows the Orchestrator to act on review findings programmatically.

### 9.4 The Explain Yourself Protocol

When the Review Agent finds a critical issue, it does not just report the conflict. It asks the responsible agent to **explain its reasoning**. Why did you name this endpoint what you named it? What assumption were you working from?

The agent responds with a structured justification. The Review Agent then presents both the conflict and the justification to the Orchestrator, which decides whether the conflict is a genuine problem or whether the agent's reasoning reveals that the contract was the one that needs updating. This makes the system's decisions auditable — you can always trace exactly why a particular choice was made.

### 9.5 The Conflict Resolution Agent

For critical conflicts that the Review Agent identifies but cannot automatically resolve, a dedicated **Conflict Resolution Agent** engages. It is given both sides of the conflict and asked to produce two resolution options with trade-off analysis. Option A might be: rename Agent 2's endpoint to match Agent 1's expectation. Option B might be: add an adapter layer in Agent 1 that translates between the two names. The Conflict Resolution Agent recommends the lower-risk option — usually the adapter pattern — and applies it automatically. Both options and the decision rationale are logged for the audit trail.

---

## Part 10 — The Merge Coordinator

Once all agents pass the Review Agent's check, the Merge Coordinator handles the final integration. This is not just running `git merge` repeatedly — it is a careful, ordered process.

### 10.1 Topological Merge Order

Branches are merged in the same order the DAG computed: API first (because everything else depends on it), then CRDT (depends on API), then frontend (depends on both API and CRDT), then tests (depends on everything). This order ensures that when each branch is merged, all of its dependencies are already present in main.

### 10.2 Post-Merge Test Runs

After each merge, the full test suite runs — Pytest for the backend, Jest for the frontend. If a test suite run fails, the Merge Coordinator does not just stop and ask a human what to do. It identifies which agent's code caused the failure by running `git bisect` programmatically, then constructs a targeted fix prompt for that agent and re-queues only that agent's branch. The fixed branch goes back through the Review Agent before being re-merged.

### 10.3 The Final Gate

The final merge to main only happens when all tests pass on the fully integrated codebase. Until that point, main stays clean. This is a strong guarantee: the code that ends up in main has been built by parallel agents, reviewed for semantic conflicts, merged in the correct dependency order, and tested at every step.

---

## Part 11 — The Epistemic State Machine

This is the most conceptually original part of the system. Most orchestration systems track agents as simply "running" or "done." The epistemic state machine tracks what each agent **knows**, what it is **assuming**, and how **confident** it is in its work.

### 11.1 The Four States

| State | What It Means |
|---|---|
| `SPECULATING` | The agent is working, but some or all of its work is based on assumptions rather than confirmed information. This happens when speculative execution is active. |
| `CONFIRMED` | All of the agent's dependencies have been resolved and validated. Everything it has built is based on confirmed contracts and decisions. |
| `DIVERGED` | The agent has learned something that contradicts an earlier assumption. Its work may need to be partially revised. |
| `RECONCILING` | The agent is actively applying a revision to fix a divergence. It knows what changed and is applying a surgical fix. |

### 11.2 How the Orchestrator Uses These States

- An agent in `SPECULATING` state is given lower merge priority than one in `CONFIRMED` state — because its work might change.
- An agent that transitions to `DIVERGED` automatically triggers the Review Agent for that branch — because divergence means the earlier review may no longer be valid.
- An agent in `RECONCILING` state gets high scheduling priority — because getting it back to `CONFIRMED` quickly unblocks everything that depends on it.

Beyond scheduling, the epistemic state machine makes the system **debuggable**. When something goes wrong, you can look at the state history and immediately understand what each agent knew at what point in time, and what assumption led to the problem.

---

## Part 12 — The Observability Dashboard

The dashboard is what judges will see during the demo. It is built with the Python `rich` library and renders in the terminal in real time.

### 12.1 What the Dashboard Shows

- A **live DAG diagram** where each node represents a task. Nodes light up as agents complete them. The current topological execution level is highlighted.
- Each agent's current **epistemic state** shown with color coding: gray for `SPECULATING`, green for `CONFIRMED`, orange for `DIVERGED`, yellow for `RECONCILING`, blue for complete.
- The current **semantic version manifest** — a live table showing the version number of every interface in the system.
- A **scrolling log** of Review Agent findings as they happen — conflicts detected, resolutions applied, re-queues triggered.
- A **live timer** showing elapsed wall-clock time for the parallel build versus the estimated sequential build time.

### 12.2 The Time Travel Feature

The dashboard includes a **replay mode** that lets you pause the demo and rewind through the entire build process. You can show judges: here is the exact moment Agent 3 went `DIVERGED`, here is the Review Agent catching the semantic conflict, here is the Conflict Resolution Agent proposing the adapter pattern fix, here is Agent 3 transitioning back to `CONFIRMED`. This is the narrative of the system made visible.

> **Demo Strategy:** The application you are demoing is not the Markdown editor. The Markdown editor is proof the system works. What you are actually demoing is the orchestration system itself — the dashboard, the parallel execution, the semantic conflict detection, and the time comparison at the end. End with: *"This application would take one agent 4 hours to build single-threaded. Our swarm built it in 47 minutes."*

---

## Part 13 — Repository Structure

The monorepo is organized so that every component has a clear home and agents cannot accidentally write to each other's directories.

| Directory / File | Contents and Purpose |
|---|---|
| `/orchestrator/` | All Python orchestration scripts: `generate_manifest.py`, `dag_orchestrator.py`, `run_agents.py`, `review_agent.py`, `merge_coordinator.py`, `speculative_scheduler.py`, `dashboard.py` |
| `/agents/{agent_id}/` | One subdirectory per agent containing `prompt.md` (the agent's instructions) and any revision history files appended by the Review Agent. |
| `/shared/contracts/` | The immutable contract files: `openapi_spec.yaml`, `websocket_messages.ts`, `yjs_document_schema.ts`. Managed exclusively by the Orchestrator. |
| `/shared/team_context.md` | The shared whiteboard. Every agent reads this on startup and writes to it when making interface decisions. |
| `/shared/semantic_versions.json` | The live version manifest tracking the current version of every major interface. |
| `/app/frontend/` | The React application. Written exclusively by Agent 1. |
| `/app/backend/` | The FastAPI application. Written exclusively by Agent 2. |
| `/app/crdt/` | The Yjs integration layer. Written exclusively by Agent 3. |
| `/app/tests/` | The test suite. Written exclusively by Agent 4. |
| `/.devswarm/` | DevSwarm configuration files specifying branch names, agent configurations, and worktree settings. |

---

## Part 14 — Phased Implementation Plan

Given hackathon time constraints, work is organized into three phases ordered by what is essential versus what adds extra points.

### PHASE 1 — Must Have: Core Orchestration

These components must work for the system to function at all. Build these first.

**Step 1: Contract-First Setup**
Generate the three contract documents (OpenAPI spec, WebSocket message types, Yjs document schema) and commit them to `/shared/contracts/`. Initialize `team_context.md` and `semantic_versions.json` as empty documents. This takes about 30 minutes and unblocks everything else.

**Step 2: Task Manifest Generation**
Build `generate_manifest.py`. Call the Claude API with the project description and the contracts. Validate the output is valid JSON matching the required schema. Run cycle detection on the dependency graph. Log the manifest to a human-readable file so you can inspect it.

**Step 3: DAG Orchestrator**
Build the `DagOrchestrator` class with Kahn's algorithm. Implement `get_ready_tasks()` and `mark_complete()`. Write a unit test that verifies the correct parallel batches are identified for a known manifest. This is the most critical component — get it right before touching anything else.

**Step 4: DevSwarm Branch Setup**
Write `setup_branches.sh` that reads the manifest and uses DevSwarm's CLI to create one git worktree per task, all branching from the same base commit on main. Verify that each worktree is fully isolated.

**Step 5: Agent Prompt Engineering**
Write the `prompt.md` file for each of the four agents. Each prompt must have the four mandatory sections (Role, Context, Task, Completion Protocol). The Completion Protocol section is especially important — without it, agents will not update the shared context and the system breaks down.

**Step 6: Parallel Execution**
Build `run_agents.py`. It reads the ready tasks from the Orchestrator and launches DevSwarm sessions for each one simultaneously. It polls for completion by watching for the `.agent_complete` sentinel file. When it detects completion, it calls `mark_complete()` and launches the next batch.

**Step 7: Basic Review Agent**
Build the first version of `review_agent.py` that extracts the git diff of a completed branch and runs it through Claude with instructions to check for interface mismatches. At this stage, it can output findings to a log file even if it does not auto-apply fixes yet.

**Step 8: Merge Coordinator**
Build `merge_coordinator.py` that merges branches in topological order, runs the test suite after each merge, and logs failures.

**Step 9: Terminal Dashboard (Basic)**
Build a basic `rich` dashboard that shows agent status and a log of events. Even a simple version of this is essential for the demo.

---

### PHASE 2 — Should Have: Advanced Features

These components make the system genuinely impressive and score points on creative use of DevSwarm.

**Step 10: Semantic Versioning System**
Implement the full `semantic_versions.json` update cycle. Make each agent read and write version numbers as part of the Completion Protocol. Make the Review Agent use version mismatches as its primary fast-path conflict signal.

**Step 11: Conflict Resolution Agent**
Extend `review_agent.py` so that when it finds a critical conflict, it engages the Conflict Resolution Agent to propose and auto-apply a resolution. Log the decision and rationale.

**Step 12: Speculative Execution**
Build the `SpeculativeScheduler` class. Implement the diff-and-threshold logic for accepting or rejecting speculative work. Implement the Incremental Reconciliation targeted patch prompt generation.

**Step 13: Explain Yourself Protocol**
Add the justification request-response cycle to the Review Agent. Store the justification logs in a structured format for the audit trail.

**Step 14: Vector Clock Causal Consistency**
Add vector clock timestamps to `team_context.md` entries. Implement the dependency tracing that ensures agents always have the full causal context of anything they read.

---

### PHASE 3 — Nice to Have: Polish and Depth

These components add intellectual depth and make the demo more memorable.

**Step 15: Full Epistemic State Machine**
Implement the four-state machine (`SPECULATING`, `CONFIRMED`, `DIVERGED`, `RECONCILING`) for each agent. Have the Orchestrator use these states for scheduling priority decisions. Display them in the dashboard.

**Step 16: Agent Skill Specialization**
Add complexity scoring to the Task Manifest. Implement dynamic compute budget allocation based on task complexity scores.

**Step 17: Time Travel Dashboard**
Add replay mode to the dashboard. Record all state transitions to a log file during the build and allow replaying them at demo time.

**Step 18: README Documentation**
Write the README section called *"How the swarm built itself"* with the actual DAG diagram, the timeline of agent start and finish times, the Review Agent's findings log, and the single-threaded versus parallel time comparison table.

---

## Part 15 — The Winning Narrative

How you frame this project matters as much as what you build. Here is the exact narrative arc for the demo and documentation:

### 15.1 The Opening

Every AI coding tool today is a single-threaded autocomplete. One human, one AI, one task at a time. We asked a different question: *what if the AI was not the assistant — what if the AI was the entire engineering team?*

### 15.2 The Conceptual Bridges

We did not invent our ideas. We borrowed them from the best engineering thinking of the last 60 years. Speculative execution comes from how modern CPUs process instructions. Causal consistency comes from distributed database theory. Contract-first development comes from API design. The epistemic state machine is our own contribution — a way of reasoning formally about what each agent knows versus what it assumes.

### 15.3 The Demo Sequence

1. Show the empty repository and the plain-English project description.
2. Show the Task Manifest being generated and the DAG being drawn.
3. Show the contracts being generated and committed before any agent writes code.
4. Start the parallel execution and show the dashboard with all four agents running simultaneously.
5. Pause and replay the moment the Review Agent catches a semantic conflict between Agent 1 and Agent 2.
6. Show the Conflict Resolution Agent proposing and applying the fix automatically.
7. Show the final merge happening in topological order with all tests passing.
8. End with the time comparison: single-threaded estimated time versus actual parallel wall-clock time.

### 15.4 The Closing Line

> *The Markdown editor is the proof. The orchestration system is the product. And the insight is simple: the bottleneck in software development was never intelligence — it was parallelism. We fixed the bottleneck.*

---

*PolyAgent CI — Implementation Plan*
*DevSwarm Hackathon — Orchestrate the Swarm*
