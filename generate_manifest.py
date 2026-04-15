"""
PolyAgent CI — Manifest Generator

Calls Gemini API (primary) / Groq / Mistral with a project description
to generate a JSON Task Manifest. Includes DFS cycle detection, JSON
schema validation, and logging.

Usage:
    python generate_manifest.py                  # Generate via AI
    python generate_manifest.py --offline        # Use hardcoded fallback
    python generate_manifest.py --provider groq  # Use specific provider
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

# ─── Constants ────────────────────────────────────────────

MANIFEST_DIR = Path(__file__).parent / "manifests"
MANIFEST_DIR.mkdir(exist_ok=True)

MANIFEST_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "required": ["task_id", "description", "agent", "branch", "depends_on"],
        "properties": {
            "task_id": {"type": "string"},
            "description": {"type": "string"},
            "agent": {"type": "string"},
            "branch": {"type": "string"},
            "depends_on": {
                "type": "array",
                "items": {"type": "string"}
            }
        }
    }
}

PROJECT_DESCRIPTION = """
You are generating a Task Manifest for a multi-agent CI system called PolyAgent CI.

The project being built is a **real-time collaborative Markdown editor** with:
- Frontend: React + CodeMirror 6 (directory: /app/frontend/)
- Backend: FastAPI + WebSockets + Redis pub/sub + JWT auth (directory: /app/backend/)
- CRDT sync: Yjs document provider (directory: /app/crdt/)
- Tests: Playwright E2E tests (directory: /app/tests/)

Each agent owns exactly ONE directory and must never touch others.

Generate a JSON array of tasks. Each task has:
- task_id: short lowercase identifier (e.g., "frontend", "backend", "crdt", "qa")
- description: detailed technical description of what the agent must build
- agent: name of the agent (e.g., "frontend-agent", "backend-agent", "crdt-agent", "qa-agent")
- branch: git branch name (e.g., "agent/frontend", "agent/backend", "agent/crdt", "agent/qa")
- depends_on: array of task_ids this task depends on

Dependency rules:
- Frontend and Backend can start simultaneously (no dependencies)
- CRDT depends on Backend (needs WebSocket endpoint definition)
- QA depends on Frontend, Backend, and CRDT (needs all components to test)

Return ONLY the JSON array, no markdown fencing, no explanation.
"""

# ─── Hardcoded Fallback Manifest ──────────────────────────

FALLBACK_MANIFEST = [
    {
        "task_id": "frontend",
        "description": "Build the React + CodeMirror 6 frontend application. Implement the editor component with markdown syntax highlighting, a toolbar for common formatting actions, and the Yjs binding via y-codemirror.next. Set up the WebSocket provider for real-time sync, implement cursor awareness to show other users' cursors with colored labels, and build the document list/management UI. Directory: /app/frontend/. Must conform to openapi_spec.yaml for REST calls and websocket_messages.ts for WebSocket communication.",
        "agent": "frontend-agent",
        "branch": "agent/frontend",
        "depends_on": []
    },
    {
        "task_id": "backend",
        "description": "Build the FastAPI backend server. Implement all REST endpoints defined in openapi_spec.yaml: auth (register/login with JWT), document CRUD, and collaborator management. Set up the WebSocket endpoint at /ws/{document_id} following the protocol in websocket_messages.ts. Integrate Redis for pub/sub (cross-process document sync) and session storage. Implement JWT middleware, rate limiting, and error handling. Directory: /app/backend/.",
        "agent": "backend-agent",
        "branch": "agent/backend",
        "depends_on": []
    },
    {
        "task_id": "crdt",
        "description": "Build the Yjs CRDT synchronization layer. Implement the server-side Yjs document manager that creates and manages Y.Doc instances per document following yjs_document_schema.ts. Build the WebSocket sync handler implementing the Yjs sync protocol (SyncStep1, SyncStep2, SyncUpdate). Set up document persistence to Redis using Y.encodeStateAsUpdate/Y.applyUpdate. Implement the awareness protocol for cursor sharing. Handle document compaction after 100 incremental updates. Directory: /app/crdt/.",
        "agent": "crdt-agent",
        "branch": "agent/crdt",
        "depends_on": ["backend"]
    },
    {
        "task_id": "qa",
        "description": "Build the comprehensive test suite using Playwright for E2E tests. Test scenarios: (1) User registration and login flow, (2) Document creation and CRUD operations, (3) Real-time collaboration - two browser windows editing simultaneously with <200ms sync, (4) Cursor awareness - verify other users' cursors appear, (5) Conflict resolution - simultaneous edits to the same paragraph, (6) Reconnection - verify sync resumes after network interruption. Also write integration tests for the WebSocket protocol and CRDT convergence. Directory: /app/tests/.",
        "agent": "qa-agent",
        "branch": "agent/qa",
        "depends_on": ["frontend", "backend", "crdt"]
    }
]


# ─── Cycle Detection ─────────────────────────────────────

def detect_cycles(tasks: list[dict]) -> list[str] | None:
    """
    DFS-based cycle detection on the task dependency graph.
    Returns the cycle path if found, None if acyclic.
    """
    task_ids = {t["task_id"] for t in tasks}
    adj = {t["task_id"]: t.get("depends_on", []) for t in tasks}

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {tid: WHITE for tid in task_ids}
    path: list[str] = []

    def dfs(tid: str) -> list[str] | None:
        color[tid] = GRAY
        path.append(tid)

        for dep in adj.get(tid, []):
            if dep not in task_ids:
                continue
            if color[dep] == GRAY:
                cycle_start = path.index(dep)
                return path[cycle_start:] + [dep]
            if color[dep] == WHITE:
                result = dfs(dep)
                if result:
                    return result

        path.pop()
        color[tid] = BLACK
        return None

    for tid in task_ids:
        if color[tid] == WHITE:
            cycle = dfs(tid)
            if cycle:
                return cycle
    return None


# ─── JSON Validation ──────────────────────────────────────

def validate_manifest(tasks: list[dict]) -> list[str]:
    """Validate manifest against schema. Returns list of error messages."""
    errors = []

    if not isinstance(tasks, list):
        return ["Manifest must be a JSON array"]

    task_ids = set()
    for i, task in enumerate(tasks):
        prefix = f"Task [{i}]"

        for field in ["task_id", "description", "agent", "branch", "depends_on"]:
            if field not in task:
                errors.append(f"{prefix}: Missing required field '{field}'")

        tid = task.get("task_id", "")
        if tid in task_ids:
            errors.append(f"{prefix}: Duplicate task_id '{tid}'")
        task_ids.add(tid)

        deps = task.get("depends_on", [])
        if not isinstance(deps, list):
            errors.append(f"{prefix}: 'depends_on' must be an array")

    # Check dependency references
    for task in tasks:
        for dep in task.get("depends_on", []):
            if dep not in task_ids:
                errors.append(f"Task '{task.get('task_id', '?')}' depends on unknown task '{dep}'")

    # Check for cycles
    cycle = detect_cycles(tasks)
    if cycle:
        errors.append(f"Dependency cycle detected: {' → '.join(cycle)}")

    return errors


# ─── AI Providers ─────────────────────────────────────────

def generate_with_gemini(prompt: str) -> str:
    """Generate manifest using Google Gemini API (new google.genai SDK)."""
    try:
        from google import genai
        from google.genai import types as gtypes
    except ImportError:
        raise ImportError("Run: pip install google-genai")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in environment")

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config=gtypes.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )
    return response.text


def generate_with_groq(prompt: str) -> str:
    """Generate manifest using Groq API."""
    from groq import Groq

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set in environment")

    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "You are a task manifest generator. Output ONLY valid JSON arrays."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    return response.choices[0].message.content


def generate_with_mistral(prompt: str) -> str:
    """Generate manifest using Mistral API."""
    from mistralai import Mistral

    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise ValueError("MISTRAL_API_KEY not set in environment")

    client = Mistral(api_key=api_key)
    response = client.chat.complete(
        model="codestral-latest",
        messages=[
            {"role": "system", "content": "You are a task manifest generator. Output ONLY valid JSON arrays."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    return response.choices[0].message.content


PROVIDERS = {
    "gemini": generate_with_gemini,
    "groq": generate_with_groq,
    "mistral": generate_with_mistral,
}


# ─── Main ─────────────────────────────────────────────────

def generate_manifest(provider: str = "gemini", offline: bool = False) -> list[dict]:
    """
    Generate a task manifest.
    Returns the validated manifest as a list of task dicts.
    """
    if offline:
        print("📋 Using offline fallback manifest...")
        tasks = FALLBACK_MANIFEST
    else:
        print(f"🤖 Generating manifest via {provider}...")
        provider_fn = PROVIDERS.get(provider)
        if not provider_fn:
            raise ValueError(f"Unknown provider '{provider}'. Choose from: {list(PROVIDERS.keys())}")

        raw = None
        try:
            raw = provider_fn(PROJECT_DESCRIPTION)
        except Exception as e:
            err_str = str(e).lower()
            if any(k in err_str for k in ["quota", "429", "exhausted", "resource_exhausted"]):
                print(f"  [WARN] {provider} quota exceeded. Auto-falling back to groq...")
                try:
                    raw = generate_with_groq(PROJECT_DESCRIPTION)
                    print("  [OK] Groq fallback succeeded.")
                except Exception as e2:
                    print(f"  [WARN] Groq also failed: {e2}. Using offline manifest.")
            else:
                print(f"  [ERROR] AI call failed: {e}")
                print("  Falling back to offline manifest...")

        if raw is not None:
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    tasks = data.get("tasks", data.get("manifest", []))
                else:
                    tasks = data
            except json.JSONDecodeError as e:
                print(f"  [ERROR] Failed to parse AI response: {e}")
                print("  Falling back to offline manifest...")
                raw = None

        if raw is None:
            tasks = FALLBACK_MANIFEST

    # Validate
    errors = validate_manifest(tasks)
    if errors:
        print(f"❌ Manifest validation failed:")
        for err in errors:
            print(f"   • {err}")
        sys.exit(1)

    print(f"✅ Manifest validated: {len(tasks)} tasks, no cycles")
    return tasks


def save_manifest(tasks: list[dict], label: str = "") -> Path:
    """Save manifest to disk with timestamp."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{label}" if label else ""
    filename = f"manifest_{timestamp}{suffix}.json"
    filepath = MANIFEST_DIR / filename

    with open(filepath, "w") as f:
        json.dump({"tasks": tasks, "generated_at": datetime.now().isoformat()}, f, indent=2)

    print(f"💾 Manifest saved to: {filepath}")
    return filepath


def main():
    parser = argparse.ArgumentParser(description="PolyAgent CI — Manifest Generator")
    parser.add_argument("--offline", action="store_true", help="Use hardcoded fallback manifest (no API call)")
    parser.add_argument("--provider", default="gemini", choices=["gemini", "groq", "mistral"],
                        help="AI provider to use (default: gemini)")
    parser.add_argument("--output", type=str, help="Custom output path for the manifest")
    args = parser.parse_args()

    tasks = generate_manifest(provider=args.provider, offline=args.offline)

    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump({"tasks": tasks, "generated_at": datetime.now().isoformat()}, f, indent=2)
        print(f"💾 Manifest saved to: {path}")
    else:
        save_manifest(tasks, label=args.provider if not args.offline else "offline")

    # Pretty print
    print("\n📊 Task Manifest:")
    print("─" * 60)
    for task in tasks:
        deps = ", ".join(task["depends_on"]) if task["depends_on"] else "(none)"
        print(f"  {task['task_id']:12s} │ {task['agent']:18s} │ deps: {deps}")
    print("─" * 60)


if __name__ == "__main__":
    main()
