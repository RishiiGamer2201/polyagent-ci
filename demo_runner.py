"""
PolyAgent CI — Complete Demo Runner

Runs the full hackathon demo sequence end-to-end.
Opens terminals, runs scripts in order, coordinates the demo flow.

Usage:
    python demo_runner.py              # Full interactive demo
    python demo_runner.py --step 3    # Jump to a specific demo step
    python demo_runner.py --fast      # Reduced delays for quick demo
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

MANIFESTS = list(Path("manifests").glob("*_offline.json")) if Path("manifests").exists() else []
MANIFEST = str(MANIFESTS[0]) if MANIFESTS else "manifests/manifest_offline.json"

STEPS = [
    {
        "num": 1,
        "title": "Generate Task Manifest",
        "desc": "Convert plain-English project description into a machine-readable DAG plan.",
        "cmd": ["python", "generate_manifest.py", "--offline"],
        "wait": 3,
    },
    {
        "num": 2,
        "title": "Run DAG Orchestrator Tests",
        "desc": "Verify Kahn's algorithm correctly identifies parallel batches.",
        "cmd": ["python", "-m", "pytest", "test_dag_orchestrator.py", "-v"],
        "wait": 3,
    },
    {
        "num": 3,
        "title": "Set Up Git Worktrees",
        "desc": "Create one isolated git branch per agent — all from the same base commit.",
        "cmd": ["powershell", "-File", "setup_branches.ps1",
                "-ManifestPath", MANIFEST, "-Clean"],
        "wait": 3,
        "skip_if_no_git": True,
    },
    {
        "num": 4,
        "title": "Launch Terminal Dashboard",
        "desc": "THE CENTERPIECE — animated show of all 4 agents with epistemic states.",
        "cmd": ["python", "dashboard.py", "--demo-mode", "--timeout", "28"],
        "wait": 0,
        "background": False,
    },
    {
        "num": 5,
        "title": "Review Agent — Catches Semantic Conflict",
        "desc": "AI reviews frontend diff, finds /api/docs vs /documents mismatch.",
        "cmd": ["python", "review_agent.py", "--review-all", "--demo-mode"],
        "wait": 2,
    },
    {
        "num": 6,
        "title": "Conflict Resolution — Auto-Apply Lower Risk Fix",
        "desc": "Two options with trade-off analysis. Lower risk auto-applied.",
        "cmd": ["python", "conflict_resolver.py", "--demo-mode"],
        "wait": 2,
    },
    {
        "num": 7,
        "title": "Speculative Execution Demo",
        "desc": "CRDT Agent started early on assumptions — 100% similar, work KEPT.",
        "cmd": ["python", "speculative_scheduler.py", "--demo-mode"],
        "wait": 2,
    },
    {
        "num": 8,
        "title": "Topological Merge — All Tests Passing",
        "desc": "Merge in order: Backend -> CRDT -> Frontend -> QA.",
        "cmd": ["python", "merge_coordinator.py",
                "--manifest", MANIFEST, "--demo-mode"],
        "wait": 2,
    },
]


def separator(title: str = "") -> None:
    width = 62
    print("\n" + "=" * width)
    if title:
        pad = (width - len(title) - 4) // 2
        print(" " * pad + f"  {title}  " + " " * pad)
        print("=" * width)
    print()


def pause(label: str = "Press ENTER to continue...") -> None:
    input(f"\n  --> {label}")


def run_step(step: dict, fast: bool = False) -> bool:
    """Execute one demo step. Returns True on success."""
    separator(f"STEP {step['num']}: {step['title']}")
    print(f"  {step['desc']}")
    print()

    # Skip git operations if not in a git repo
    if step.get("skip_if_no_git"):
        result = subprocess.run(["git", "status"], capture_output=True)
        if result.returncode != 0:
            print("  (Skipping — not in a git repository)")
            return True

    print(f"  Running: {' '.join(step['cmd'])}\n")
    time.sleep(0.5 if fast else 1)

    result = subprocess.run(step["cmd"])
    success = result.returncode == 0

    if success:
        print(f"\n  STEP {step['num']} COMPLETE")
    else:
        print(f"\n  STEP {step['num']} had non-zero exit (may be normal for demo)")

    wait = (step["wait"] // 2) if fast else step["wait"]
    if wait > 0:
        time.sleep(wait)

    return success


def main():
    parser = argparse.ArgumentParser(description="PolyAgent CI — Demo Runner")
    parser.add_argument("--step", type=int, default=1,
                        help="Start from this step number (default: 1)")
    parser.add_argument("--fast", action="store_true",
                        help="Reduced delays for quick demo")
    parser.add_argument("--auto", action="store_true",
                        help="Skip ENTER prompts (run fully automatic)")
    args = parser.parse_args()

    separator("POLYAGENT CI — HACKATHON DEMO")
    print("  Multi-Agent Orchestration Platform")
    print("  4 parallel AI agents | DAG scheduling | Semantic review")
    print()
    print("  Demo sequence:")
    for step in STEPS:
        marker = "  " if step["num"] < args.step else "->"
        print(f"  {marker} Step {step['num']}: {step['title']}")

    if not args.auto:
        pause("Ready? Press ENTER to start the demo...")

    # Generate manifest if needed
    if not MANIFESTS:
        print("\n  Generating offline manifest first...")
        subprocess.run(["python", "generate_manifest.py", "--offline"])

    # Run steps
    for step in STEPS:
        if step["num"] < args.step:
            continue

        if not args.auto:
            pause(f"Press ENTER to run Step {step['num']}: {step['title']}")

        run_step(step, fast=args.fast)

    # Final closing
    separator("DEMO COMPLETE")
    print()
    print("  The Markdown editor is the proof.")
    print("  The orchestration system is the product.")
    print("  The insight: the bottleneck was never intelligence — it was parallelism.")
    print()
    print("  PolyAgent CI fixed the bottleneck.")
    print()


if __name__ == "__main__":
    main()
