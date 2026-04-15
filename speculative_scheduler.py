"""
PolyAgent CI — Speculative Scheduler

Enables blocked agents to start early by generating best-guess
assumption documents. When the blocking task completes, diffs
actual output against assumptions:
  - ≥80% similar → valid (speculative work is kept)
  - <80% similar → generate incremental reconciliation prompt

Usage:
    python speculative_scheduler.py --manifest manifests/manifest_*.json
    python speculative_scheduler.py --demo-mode
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from dotenv import load_dotenv

import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

# ─── Constants ────────────────────────────────────────────

SIMILARITY_THRESHOLD = 0.80  # 80% = valid speculation
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)
SPECULATION_LOG = LOGS_DIR / "speculation_log.json"


# ─── Assumption Document Templates ───────────────────────

ASSUMPTION_TEMPLATES = {
    "crdt": {
        "assumption_for": "crdt",
        "blocked_by": "backend",
        "description": "Best-guess assumptions about Backend Agent's WebSocket implementation for CRDT Agent to start early.",
        "assumptions": {
            "websocket_endpoint": "/ws/{document_id}?token=<jwt>",
            "binary_protocol": "Yjs sync protocol — byte 0 is message type, remaining bytes are Yjs payload",
            "message_types": {
                "SYNC_STEP_1": 0,
                "SYNC_STEP_2": 1,
                "SYNC_UPDATE": 2,
                "AWARENESS_UPDATE": 3,
            },
            "redis_keys": {
                "state": "ydoc:{docId}:state",
                "updates": "ydoc:{docId}:updates",
                "awareness": "ydoc:{docId}:awareness",
            },
            "auth_method": "JWT token passed as query parameter",
            "framework": "FastAPI with WebSocket support",
        },
        "confidence": 0.90,
        "source": "Derived from shared contracts (openapi_spec.yaml, websocket_messages.ts)",
    },
    "qa": {
        "assumption_for": "qa",
        "blocked_by": "frontend,backend,crdt",
        "description": "Best-guess assumptions about all agents' implementations for QA Agent to start writing test scaffolding.",
        "assumptions": {
            "frontend": {
                "url": "http://localhost:3000",
                "editor_selector": "[data-testid='editor']",
                "login_page": "/login",
                "documents_page": "/documents",
                "framework": "React + CodeMirror 6",
            },
            "backend": {
                "url": "http://localhost:8000",
                "auth_endpoint": "POST /auth/login",
                "documents_endpoint": "GET /documents",
                "websocket_endpoint": "/ws/{document_id}",
            },
            "crdt": {
                "sync_protocol": "Yjs binary sync",
                "awareness": "Yjs awareness protocol",
                "shared_types": {"content": "Y.Text", "metadata": "Y.Map"},
            },
        },
        "confidence": 0.85,
        "source": "Derived from shared contracts and team_context.md",
    },
}


# ─── Similarity Checker ──────────────────────────────────

def compute_similarity(assumption: dict | str, actual: dict | str) -> float:
    """
    Compute similarity between assumption and actual output.
    Uses SequenceMatcher on JSON serialization for structural comparison.
    """
    if isinstance(assumption, dict):
        assumption_str = json.dumps(assumption, sort_keys=True, indent=2)
    else:
        assumption_str = str(assumption)

    if isinstance(actual, dict):
        actual_str = json.dumps(actual, sort_keys=True, indent=2)
    else:
        actual_str = str(actual)

    return SequenceMatcher(None, assumption_str, actual_str).ratio()


def compute_field_similarity(assumption: dict, actual: dict) -> dict:
    """
    Compute per-field similarity between assumption and actual.
    Returns {field: similarity_ratio} for each field in assumption.
    """
    results = {}
    all_keys = set(list(assumption.keys()) + list(actual.keys()))

    for key in all_keys:
        a_val = assumption.get(key)
        b_val = actual.get(key)

        if a_val is None and b_val is None:
            results[key] = 1.0
        elif a_val is None or b_val is None:
            results[key] = 0.0
        elif isinstance(a_val, dict) and isinstance(b_val, dict):
            # Recursive comparison
            sub_results = compute_field_similarity(a_val, b_val)
            results[key] = sum(sub_results.values()) / max(len(sub_results), 1)
        else:
            results[key] = 1.0 if str(a_val) == str(b_val) else 0.0

    return results


# ─── Reconciliation Prompt Generator ─────────────────────

def generate_reconciliation_prompt(
    task_id: str,
    assumption: dict,
    actual: dict,
    field_diffs: dict,
) -> str:
    """
    Generate an incremental reconciliation prompt when speculation
    is invalid (similarity < 80%).
    
    This is a SURGICAL PATCH — not a full restart.
    """
    diverged_fields = [
        f"- **{field}**: assumed `{json.dumps(assumption.get(field, 'N/A'))}`, "
        f"actual `{json.dumps(actual.get(field, 'N/A'))}` "
        f"(similarity: {sim:.0%})"
        for field, sim in field_diffs.items()
        if sim < 0.8
    ]

    prompt = f"""## Incremental Reconciliation Required — {task_id}

Your speculative work was based on assumptions that diverged from actual output.
**This is NOT a full restart.** Apply targeted patches only to the diverged areas.

### Diverged Fields:
{chr(10).join(diverged_fields)}

### Your Assumptions (what you built against):
```json
{json.dumps(assumption, indent=2)}
```

### Actual Output (what was actually implemented):
```json
{json.dumps(actual, indent=2)}
```

### Instructions:
1. For each diverged field, identify the specific code that uses the assumed value
2. Replace ONLY the assumed values with the actual values
3. Run your local tests to verify the patches
4. Do NOT restructure or rewrite unaffected code

This is a surgical patch, not a rewrite.
"""
    return prompt


# ─── Speculative Scheduler ───────────────────────────────

class SpeculativeScheduler:
    """
    Manages speculative execution for blocked tasks.
    
    Flow:
    1. When a task is blocked, generate assumption documents
    2. Allow the blocked task to start with assumptions
    3. When the blocking task completes, compare actual vs assumed
    4. If ≥80% similar → keep speculative work
    5. If <80% similar → generate reconciliation prompt
    """

    def __init__(self, demo_mode: bool = False):
        self.demo_mode = demo_mode
        self.assumptions: dict[str, dict] = {}
        self.results: list[dict] = []

    def generate_assumptions(self, task_id: str) -> dict:
        """Generate assumption documents for a blocked task."""
        print(f"\n  📝 Generating assumptions for: {task_id}")

        if task_id in ASSUMPTION_TEMPLATES:
            assumption = ASSUMPTION_TEMPLATES[task_id]
        else:
            assumption = {
                "assumption_for": task_id,
                "description": f"Generic assumptions for {task_id}",
                "assumptions": {},
                "confidence": 0.5,
            }

        self.assumptions[task_id] = assumption
        print(f"     Confidence: {assumption.get('confidence', 0):.0%}")
        print(f"     Source: {assumption.get('source', 'unknown')}")

        return assumption

    def validate_speculation(self, task_id: str, actual_output: dict) -> dict:
        """
        Compare actual output against assumptions.
        Returns validation result.
        """
        print(f"\n  🔍 Validating speculation for: {task_id}")

        assumption = self.assumptions.get(task_id, {})
        assumed_data = assumption.get("assumptions", {})

        # Compute overall similarity
        overall_sim = compute_similarity(assumed_data, actual_output)

        # Compute per-field similarity
        field_sims = compute_field_similarity(assumed_data, actual_output)

        # Decision
        is_valid = overall_sim >= SIMILARITY_THRESHOLD

        result = {
            "task_id": task_id,
            "timestamp": datetime.now().isoformat(),
            "overall_similarity": round(overall_sim, 4),
            "threshold": SIMILARITY_THRESHOLD,
            "is_valid": is_valid,
            "field_similarities": {k: round(v, 4) for k, v in field_sims.items()},
            "decision": "KEEP" if is_valid else "RECONCILE",
        }

        if is_valid:
            print(f"     ✅ Speculation VALID — {overall_sim:.0%} similar (threshold: {SIMILARITY_THRESHOLD:.0%})")
            print(f"     📋 Speculative work can be kept as-is")
        else:
            print(f"     ⚠️  Speculation INVALID — {overall_sim:.0%} similar (threshold: {SIMILARITY_THRESHOLD:.0%})")
            print(f"     📝 Generating reconciliation prompt...")

            prompt = generate_reconciliation_prompt(
                task_id, assumed_data, actual_output, field_sims
            )
            result["reconciliation_prompt"] = prompt

            # Save prompt to file
            prompt_path = LOGS_DIR / f"reconciliation_{task_id}.md"
            prompt_path.write_text(prompt)
            print(f"     📋 Prompt saved to: {prompt_path}")

        self.results.append(result)
        return result

    def run_demo(self) -> None:
        """Run the demo scenario."""
        print("\n" + "=" * 60)
        print("  PolyAgent CI — Speculative Scheduler Demo")
        print("=" * 60)

        # 1. Generate assumptions for CRDT (blocked by Backend)
        crdt_assumption = self.generate_assumptions("crdt")

        # 2. Simulate Backend completing with output that matches well
        actual_backend_for_crdt = {
            "websocket_endpoint": "/ws/{document_id}?token=<jwt>",
            "binary_protocol": "Yjs sync protocol — byte 0 is message type, remaining bytes are Yjs payload",
            "message_types": {
                "SYNC_STEP_1": 0,
                "SYNC_STEP_2": 1,
                "SYNC_UPDATE": 2,
                "AWARENESS_UPDATE": 3,
            },
            "redis_keys": {
                "state": "ydoc:{docId}:state",
                "updates": "ydoc:{docId}:updates",
                "awareness": "ydoc:{docId}:awareness",
            },
            "auth_method": "JWT token passed as query parameter",
            "framework": "FastAPI with WebSocket support",  # Matches exactly
        }

        # 3. Validate CRDT speculation (should PASS — high similarity)
        crdt_result = self.validate_speculation("crdt", actual_backend_for_crdt)

        # 4. Generate assumptions for QA
        qa_assumption = self.generate_assumptions("qa")

        # 5. Simulate partial mismatch for QA (frontend URL different)
        actual_for_qa = {
            "frontend": {
                "url": "http://localhost:5173",  # Vite default, not 3000!
                "editor_selector": "[data-testid='markdown-editor']",  # Different!
                "login_page": "/login",
                "documents_page": "/documents",
                "framework": "React + CodeMirror 6",
            },
            "backend": {
                "url": "http://localhost:8000",
                "auth_endpoint": "POST /auth/login",
                "documents_endpoint": "GET /documents",
                "websocket_endpoint": "/ws/{document_id}",
            },
            "crdt": {
                "sync_protocol": "Yjs binary sync",
                "awareness": "Yjs awareness protocol",
                "shared_types": {"content": "Y.Text", "metadata": "Y.Map"},
            },
        }

        # 6. Validate QA speculation (might fail on frontend details)
        qa_result = self.validate_speculation("qa", actual_for_qa)

        # Summary
        print(f"\n{'=' * 60}")
        print("  Speculation Summary:")
        for r in self.results:
            icon = "✅" if r["is_valid"] else "⚠️"
            print(f"    {icon} {r['task_id']}: {r['overall_similarity']:.0%} similar → {r['decision']}")
        print(f"{'=' * 60}")

        self._save_log()

    def _save_log(self) -> None:
        with open(SPECULATION_LOG, "w") as f:
            json.dump(self.results, f, indent=2)
        print(f"\n  📋 Speculation log saved to: {SPECULATION_LOG}")


# ─── CLI ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="PolyAgent CI — Speculative Scheduler")
    parser.add_argument("--manifest", help="Path to manifest JSON")
    parser.add_argument("--demo-mode", action="store_true", help="Run demo scenario")
    args = parser.parse_args()

    scheduler = SpeculativeScheduler(demo_mode=args.demo_mode)

    if args.demo_mode:
        scheduler.run_demo()
    else:
        print("  ℹ️  Speculative scheduler runs as part of the orchestration pipeline.")
        print("  Use --demo-mode to see an interactive demo.")


if __name__ == "__main__":
    main()
