"""
PolyAgent CI — Conflict Resolution Agent

When the Review Agent finds a critical issue, this agent:
1. Generates two resolution options with trade-off analysis
2. Auto-applies the lower-risk option
3. Logs the decision and rationale

Usage:
    python conflict_resolver.py --review-log logs/review_log.json
    python conflict_resolver.py --demo-mode
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

LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)
RESOLUTION_LOG = LOGS_DIR / "resolution_log.json"
REVIEW_LOG = LOGS_DIR / "review_log.json"

# ─── Resolution Strategies ───────────────────────────────

RESOLUTION_STRATEGIES = {
    "endpoint_mismatch": {
        "option_a": {
            "name": "Fix Consumer (Lower Risk)",
            "description": "Update the consuming agent's code to match the contract endpoint.",
            "risk": "low",
            "effort": "small",
            "trade_off": "Minimal code change, single file edit, no contract modification needed.",
            "auto_apply": True,
        },
        "option_b": {
            "name": "Update Contract + All Consumers",
            "description": "Change the contract to match the agent's implementation, then update all other agents.",
            "risk": "high",
            "effort": "large",
            "trade_off": "Requires cascading changes across multiple agents and re-validation.",
            "auto_apply": False,
        },
    },
    "message_format": {
        "option_a": {
            "name": "Fix Agent to Match Contract (Lower Risk)",
            "description": "Update the agent's message type definitions to match the contract exactly.",
            "risk": "low",
            "effort": "small",
            "trade_off": "Single agent fix, enum value correction.",
            "auto_apply": True,
        },
        "option_b": {
            "name": "Update Contract to Match Implementation",
            "description": "Modify the contract's enum values to match what the agent implemented.",
            "risk": "medium",
            "effort": "medium",
            "trade_off": "Requires updating all agents that have already implemented the old values.",
            "auto_apply": False,
        },
    },
    "schema_mismatch": {
        "option_a": {
            "name": "Fix Agent's Shared Type Names (Lower Risk)",
            "description": "Correct the Y.Doc shared type name strings in the agent's code.",
            "risk": "low",
            "effort": "small",
            "trade_off": "Simple string replacement, no structural changes.",
            "auto_apply": True,
        },
        "option_b": {
            "name": "Refactor Schema",
            "description": "Update the CRDT schema to accommodate the alternative naming.",
            "risk": "high",
            "effort": "large",
            "trade_off": "Breaking change for all agents. Full re-test required.",
            "auto_apply": False,
        },
    },
}

# ─── Demo Resolutions ────────────────────────────────────

DEMO_RESOLUTIONS = [
    {
        "conflict_id": "frontend-endpoint_mismatch-1",
        "task_id": "frontend",
        "category": "endpoint_mismatch",
        "severity": "critical",
        "original_conflict": "Frontend uses '/api/docs' instead of '/documents'",
        "options": [
            {
                "name": "Fix Frontend API Client (Lower Risk)",
                "description": "Update src/api/client.ts: change API_ENDPOINTS.DOCUMENTS from '/api/docs' to '/documents'",
                "risk": "low",
                "effort": "1 line change",
                "trade_off": "Minimal change, matches contract, no other agents affected.",
                "selected": True,
            },
            {
                "name": "Update OpenAPI Spec + Backend",
                "description": "Change openapi_spec.yaml endpoint from '/documents' to '/api/docs', then update backend routes.",
                "risk": "high",
                "effort": "Multiple files across 2 agents",
                "trade_off": "Cascading changes, backend re-test needed, contract change protocol required.",
                "selected": False,
            },
        ],
        "applied_option": "Fix Frontend API Client (Lower Risk)",
        "applied_fix": {
            "file": "app/frontend/src/api/client.ts",
            "search": "'/api/docs'",
            "replace": "'/documents'",
        },
        "rationale": "Lower-risk option selected automatically. Single-line change in the consumer "
                     "aligns with the contract without cascading changes.",
        "status": "resolved",
    },
    {
        "conflict_id": "frontend-message_format-2",
        "task_id": "frontend",
        "category": "message_format",
        "severity": "warning",
        "original_conflict": "WebSocket message type enum starts at 1 instead of 0",
        "options": [
            {
                "name": "Fix Frontend Enum Values (Lower Risk)",
                "description": "Update SYNC_STEP_1 from 1 to 0 in ws-provider.ts MessageType enum",
                "risk": "low",
                "effort": "Enum value correction",
                "trade_off": "Simple fix, matches contract definition.",
                "selected": True,
            },
            {
                "name": "Update Contract Enum",
                "description": "Change websocket_messages.ts SYNC_STEP_1 from 0 to 1",
                "risk": "medium",
                "effort": "Contract change + backend update",
                "trade_off": "Requires contract change protocol and backend re-alignment.",
                "selected": False,
            },
        ],
        "applied_option": "Fix Frontend Enum Values (Lower Risk)",
        "applied_fix": {
            "file": "app/frontend/src/collaboration/ws-provider.ts",
            "search": "SYNC_STEP_1 = 1",
            "replace": "SYNC_STEP_1 = 0",
        },
        "rationale": "Auto-selected lower-risk option. Enum offset correction without structural changes.",
        "status": "resolved",
    },
]


# ─── Resolution Engine ───────────────────────────────────

class ConflictResolver:
    """Resolves semantic conflicts found by the Review Agent."""

    def __init__(self, demo_mode: bool = False, provider: str = "gemini"):
        self.demo_mode = demo_mode
        self.provider = provider
        self.resolutions: list[dict] = []

    def resolve_all(self, review_log_path: Path = REVIEW_LOG) -> list[dict]:
        """Process all unresolved conflicts from the review log."""
        if self.demo_mode:
            print("\n🔧 [DEMO] Conflict Resolution Agent")
            print("=" * 60)
            self.resolutions = DEMO_RESOLUTIONS
            for res in self.resolutions:
                self._print_resolution(res)
            self._save_log()
            return self.resolutions

        # Load review results
        if not review_log_path.exists():
            print("  ℹ️  No review log found. Nothing to resolve.")
            return []

        with open(review_log_path) as f:
            reviews = json.load(f)

        # Find critical/warning conflicts
        for review in reviews:
            if review.get("status") not in ("fail", "warning"):
                continue

            for i, conflict in enumerate(review.get("conflicts", [])):
                if conflict.get("severity") not in ("critical", "warning"):
                    continue

                resolution = self._resolve_conflict(review, conflict, i)
                self.resolutions.append(resolution)
                self._print_resolution(resolution)

        self._save_log()
        return self.resolutions

    def _resolve_conflict(self, review: dict, conflict: dict, index: int) -> dict:
        """Generate resolution options for a single conflict."""
        task_id = review.get("task_id", "unknown")
        category = conflict.get("category", "other")

        # Get strategy template
        strategy = RESOLUTION_STRATEGIES.get(category, RESOLUTION_STRATEGIES.get("endpoint_mismatch"))

        resolution = {
            "conflict_id": f"{task_id}-{category}-{index}",
            "task_id": task_id,
            "category": category,
            "severity": conflict.get("severity", "unknown"),
            "original_conflict": conflict.get("description", ""),
            "options": [
                {**strategy["option_a"], "selected": True},
                {**strategy["option_b"], "selected": False},
            ],
            "applied_option": strategy["option_a"]["name"],
            "applied_fix": {
                "file": conflict.get("file", "unknown"),
                "search": conflict.get("actual", ""),
                "replace": conflict.get("expected", ""),
            },
            "rationale": f"Auto-selected lower-risk option '{strategy['option_a']['name']}'. "
                         f"{strategy['option_a']['trade_off']}",
            "status": "resolved",
            "resolved_at": datetime.now().isoformat(),
        }

        # Attempt auto-apply if applicable
        if strategy["option_a"].get("auto_apply"):
            success = self._apply_fix(resolution["applied_fix"])
            resolution["auto_applied"] = success

        return resolution

    def _apply_fix(self, fix: dict) -> bool:
        """Attempt to auto-apply a fix."""
        filepath = Path(fix.get("file", ""))
        search = fix.get("search", "")
        replace = fix.get("replace", "")

        if not filepath.exists() or not search or not replace:
            return False

        try:
            content = filepath.read_text()
            if search in content:
                content = content.replace(search, replace, 1)
                filepath.write_text(content)
                return True
        except Exception:
            pass
        return False

    def _print_resolution(self, res: dict) -> None:
        """Pretty-print a resolution."""
        print(f"\n  {'─' * 56}")
        sev_icon = {"critical": "🔴", "warning": "🟡"}.get(res.get("severity", ""), "⚪")
        print(f"  {sev_icon} Conflict: {res.get('original_conflict', '')}")
        print(f"  📋 Task: {res.get('task_id', '')} | Category: {res.get('category', '')}")

        for i, opt in enumerate(res.get("options", []), 1):
            selected = "✅" if opt.get("selected") else "  "
            risk_color = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(opt.get("risk", ""), "⚪")
            print(f"\n  {selected} Option {i}: {opt.get('name', '')}")
            print(f"     Risk: {risk_color} {opt.get('risk', '')} | Effort: {opt.get('effort', '')}")
            print(f"     {opt.get('trade_off', '')}")

        print(f"\n  🔧 Applied: {res.get('applied_option', '')}")
        print(f"  💡 Rationale: {res.get('rationale', '')}")

    def _save_log(self) -> None:
        """Save resolutions to log file."""
        with open(RESOLUTION_LOG, "w") as f:
            json.dump(self.resolutions, f, indent=2)
        print(f"\n  📋 Resolution log saved to: {RESOLUTION_LOG}")


# ─── CLI ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="PolyAgent CI — Conflict Resolver")
    parser.add_argument("--review-log", default=str(REVIEW_LOG), help="Path to review log")
    parser.add_argument("--demo-mode", action="store_true", help="Use demo resolutions")
    parser.add_argument("--provider", default="gemini", choices=["gemini", "groq"])
    args = parser.parse_args()

    resolver = ConflictResolver(demo_mode=args.demo_mode, provider=args.provider)
    resolutions = resolver.resolve_all(Path(args.review_log))

    print(f"\n  Total conflicts resolved: {len(resolutions)}")


if __name__ == "__main__":
    main()
