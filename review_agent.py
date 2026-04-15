"""
PolyAgent CI — Review Agent

Extracts git diff of a completed branch, sends it to an AI model along with
the contract files, and checks for semantic conflicts. Outputs structured JSON.

Usage:
    python review_agent.py --task-id frontend --branch agent/frontend
    python review_agent.py --task-id frontend --demo-mode
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

# ─── Constants ────────────────────────────────────────────

CONTRACTS_DIR = Path("shared/contracts")
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)
REVIEW_LOG = LOGS_DIR / "review_log.json"

REVIEW_PROMPT_TEMPLATE = """You are a semantic code review agent for PolyAgent CI.

You are reviewing the changes made by the {agent} on branch {branch} for task {task_id}.

## Contracts (Source of Truth)

### OpenAPI Spec (REST endpoints):
```yaml
{openapi_spec}
```

### WebSocket Messages:
```typescript
{ws_messages}
```

### Yjs Document Schema:
```typescript
{yjs_schema}
```

## Git Diff to Review:
```diff
{diff}
```

## Your Job:

Check for SEMANTIC CONFLICTS — places where the agent's code deviates from the contracts or would be incompatible with other agents' work. Specifically check:

1. **Endpoint mismatches**: Does the code use the exact endpoint paths from the OpenAPI spec? (e.g., `/documents` not `/docs`)
2. **Message format mismatches**: Do WebSocket message types match the contract definitions?
3. **Schema mismatches**: Are Yjs shared type names correct (`"content"`, `"metadata"`)?
4. **Auth flow mismatches**: Is JWT handling consistent (Bearer scheme, query param for WS)?
5. **Redis key mismatches**: Do Redis key patterns match `ydoc:{{docId}}:*`?

Respond with ONLY a JSON object in this exact format:
{{
  "task_id": "{task_id}",
  "branch": "{branch}",
  "status": "pass" | "fail" | "warning",
  "conflicts": [
    {{
      "severity": "critical" | "warning" | "info",
      "category": "endpoint_mismatch" | "message_format" | "schema_mismatch" | "auth_flow" | "redis_keys" | "other",
      "file": "<filename>",
      "line": <line_number_or_null>,
      "description": "<what's wrong>",
      "expected": "<what the contract says>",
      "actual": "<what the code does>",
      "suggested_fix": "<how to fix it>"
    }}
  ],
  "summary": "<one-line summary>"
}}
"""

# ─── Seeded Demo Conflict ─────────────────────────────────

DEMO_REVIEW_RESULTS = {
    "frontend": {
        "task_id": "frontend",
        "branch": "agent/frontend",
        "status": "fail",
        "conflicts": [
            {
                "severity": "critical",
                "category": "endpoint_mismatch",
                "file": "src/api/client.ts",
                "line": 23,
                "description": "Frontend uses '/api/docs' instead of '/documents' for document listing endpoint",
                "expected": "GET /documents (per openapi_spec.yaml, operationId: listDocuments)",
                "actual": "GET /api/docs",
                "suggested_fix": "Change API_ENDPOINTS.DOCUMENTS from '/api/docs' to '/documents' in src/api/client.ts"
            },
            {
                "severity": "warning",
                "category": "message_format",
                "file": "src/collaboration/ws-provider.ts",
                "line": 87,
                "description": "WebSocket message type enum starts at 1 instead of 0",
                "expected": "SYNC_STEP_1 = 0 (per websocket_messages.ts)",
                "actual": "SYNC_STEP_1 = 1",
                "suggested_fix": "Update MessageType enum to start at 0, matching the contract"
            }
        ],
        "summary": "CRITICAL: Frontend uses wrong endpoint path '/api/docs' instead of '/documents'. WebSocket message type enum offset by 1."
    },
    "backend": {
        "task_id": "backend",
        "branch": "agent/backend",
        "status": "pass",
        "conflicts": [],
        "summary": "Backend implementation matches all contracts. No conflicts detected."
    },
    "crdt": {
        "task_id": "crdt",
        "branch": "agent/crdt",
        "status": "warning",
        "conflicts": [
            {
                "severity": "info",
                "category": "other",
                "file": "persistence.py",
                "line": 45,
                "description": "Compaction threshold is set to 50 instead of 100",
                "expected": "COMPACTION_THRESHOLD = 100 (per yjs_document_schema.ts)",
                "actual": "COMPACTION_THRESHOLD = 50",
                "suggested_fix": "Update COMPACTION_THRESHOLD to 100 to match the contract"
            }
        ],
        "summary": "Minor: Compaction threshold differs from contract (50 vs 100). Non-breaking."
    },
    "qa": {
        "task_id": "qa",
        "branch": "agent/qa",
        "status": "pass",
        "conflicts": [],
        "summary": "Test suite references all correct endpoints and message types."
    }
}


# ─── Contract Loading ─────────────────────────────────────

def load_contracts() -> dict[str, str]:
    """Load all contract files as strings."""
    contracts = {}

    openapi_path = CONTRACTS_DIR / "openapi_spec.yaml"
    ws_path = CONTRACTS_DIR / "websocket_messages.ts"
    yjs_path = CONTRACTS_DIR / "yjs_document_schema.ts"

    contracts["openapi_spec"] = openapi_path.read_text() if openapi_path.exists() else "(not found)"
    contracts["ws_messages"] = ws_path.read_text() if ws_path.exists() else "(not found)"
    contracts["yjs_schema"] = yjs_path.read_text() if yjs_path.exists() else "(not found)"

    return contracts


# ─── Git Diff Extraction ──────────────────────────────────

def get_git_diff(branch: str, base: str = "main") -> str:
    """Extract git diff of a branch against base."""
    try:
        result = subprocess.run(
            ["git", "diff", f"{base}...{branch}", "--stat", "--patch"],
            capture_output=True, text=True, cwd="."
        )
        if result.returncode != 0:
            return f"(Failed to get diff: {result.stderr.strip()})"
        return result.stdout or "(Empty diff)"
    except FileNotFoundError:
        return "(git not found)"


# ─── AI Review ────────────────────────────────────────────

def review_with_gemini(prompt: str) -> str:
    """Send review prompt to Gemini."""
    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )
    return response.text


def review_with_groq(prompt: str) -> str:
    """Send review prompt to Groq."""
    from groq import Groq

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set")

    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "You are a semantic code reviewer. Output ONLY valid JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content


REVIEW_PROVIDERS = {
    "gemini": review_with_gemini,
    "groq": review_with_groq,
}


# ─── Review Engine ────────────────────────────────────────

def review_task(
    task_id: str,
    branch: str,
    agent: str = "",
    provider: str = "gemini",
    demo_mode: bool = False,
) -> dict:
    """
    Review a completed task for semantic conflicts.
    Returns structured review result.
    """
    print(f"\n🔍 Reviewing task: {task_id} (branch: {branch})")

    if demo_mode:
        print("  📋 [DEMO MODE] Using seeded review results")
        result = DEMO_REVIEW_RESULTS.get(task_id, {
            "task_id": task_id,
            "branch": branch,
            "status": "pass",
            "conflicts": [],
            "summary": "No conflicts detected (demo mode, no seeded result)."
        })
    else:
        # Load contracts
        contracts = load_contracts()

        # Get diff
        diff = get_git_diff(branch)
        if len(diff) > 50000:
            diff = diff[:50000] + "\n... (truncated)"

        # Build prompt
        prompt = REVIEW_PROMPT_TEMPLATE.format(
            agent=agent or task_id,
            branch=branch,
            task_id=task_id,
            openapi_spec=contracts["openapi_spec"][:5000],  # Truncate for token limits
            ws_messages=contracts["ws_messages"][:5000],
            yjs_schema=contracts["yjs_schema"][:5000],
            diff=diff,
        )

        # Call AI
        review_fn = REVIEW_PROVIDERS.get(provider)
        if not review_fn:
            raise ValueError(f"Unknown provider: {provider}")

        try:
            raw = review_fn(prompt)
            result = json.loads(raw)
        except (json.JSONDecodeError, Exception) as e:
            print(f"  ❌ AI review failed: {e}")
            result = {
                "task_id": task_id,
                "branch": branch,
                "status": "error",
                "conflicts": [],
                "summary": f"Review failed: {str(e)}"
            }

    # Log result
    _log_review(result)
    _print_review(result)

    return result


def _log_review(result: dict) -> None:
    """Append review result to review_log.json."""
    log_entry = {
        "reviewed_at": datetime.now().isoformat(),
        **result,
    }

    existing = []
    if REVIEW_LOG.exists():
        try:
            with open(REVIEW_LOG) as f:
                existing = json.load(f)
        except json.JSONDecodeError:
            existing = []

    existing.append(log_entry)
    with open(REVIEW_LOG, "w") as f:
        json.dump(existing, f, indent=2)


def _print_review(result: dict) -> None:
    """Pretty-print review results to terminal."""
    status_icon = {"pass": "✅", "fail": "❌", "warning": "⚠️", "error": "💥"}.get(
        result.get("status", ""), "❓"
    )
    print(f"\n  {status_icon} Review Result: {result.get('status', 'unknown').upper()}")
    print(f"  📝 {result.get('summary', 'No summary')}")

    conflicts = result.get("conflicts", [])
    if conflicts:
        print(f"\n  Found {len(conflicts)} conflict(s):")
        for i, c in enumerate(conflicts, 1):
            sev_icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(c.get("severity", ""), "⚪")
            print(f"\n  {sev_icon} [{i}] {c.get('severity', '').upper()}: {c.get('category', '')}")
            print(f"     File: {c.get('file', 'unknown')}")
            print(f"     Issue: {c.get('description', '')}")
            print(f"     Expected: {c.get('expected', '')}")
            print(f"     Actual: {c.get('actual', '')}")
            print(f"     Fix: {c.get('suggested_fix', '')}")


# ─── CLI ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="PolyAgent CI — Review Agent")
    parser.add_argument("--task-id", default="", help="Task ID to review")
    parser.add_argument("--branch", default="", help="Branch name (default: agent/<task_id>)")
    parser.add_argument("--agent", default="", help="Agent name")
    parser.add_argument("--provider", default="gemini", choices=["gemini", "groq"])
    parser.add_argument("--demo-mode", action="store_true", help="Use seeded review results")
    parser.add_argument("--review-all", action="store_true", help="Review all tasks")
    args = parser.parse_args()

    if args.review_all:
        tasks = ["backend", "frontend", "crdt", "qa"]
        for tid in tasks:
            branch = f"agent/{tid}"
            review_task(tid, branch, provider=args.provider, demo_mode=args.demo_mode)
    elif args.task_id:
        branch = args.branch if args.branch else f"agent/{args.task_id}"
        review_task(args.task_id, branch, args.agent, args.provider, args.demo_mode)
    else:
        parser.error("Provide --task-id <id> or --review-all")


if __name__ == "__main__":
    main()
