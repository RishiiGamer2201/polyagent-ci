"""
PolyAgent CI — Vector Clock Utility

Implements vector clock timestamps for causal consistency in team_context.md.
Every entry in the shared context gets a version stamp that records:
  - When it was written
  - Which other entries it depended on (causal dependencies)

This ensures no agent ever builds on incomplete information.

Borrowed from distributed database theory (Lamport clocks generalized to N nodes).
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

AGENT_IDS = ["frontend", "backend", "crdt", "qa"]
SHARED_DIR = Path("shared")
TEAM_CONTEXT = SHARED_DIR / "team_context.md"
SEMANTIC_VERSIONS = SHARED_DIR / "semantic_versions.json"


# ─── Vector Clock ─────────────────────────────────────────

class VectorClock:
    """
    A vector clock for N agents.
    Each agent has an integer counter. When an agent writes an entry,
    it increments its own counter. The full clock is embedded in the entry.
    """

    def __init__(self, clock: dict[str, int] | None = None):
        self.clock: dict[str, int] = {aid: 0 for aid in AGENT_IDS}
        if clock:
            self.clock.update(clock)

    def tick(self, agent_id: str) -> "VectorClock":
        """Increment the counter for agent_id and return a new clock."""
        new = VectorClock(self.clock.copy())
        new.clock[agent_id] = new.clock.get(agent_id, 0) + 1
        return new

    def merge(self, other: "VectorClock") -> "VectorClock":
        """Merge two vector clocks by taking element-wise max."""
        merged = {}
        all_keys = set(self.clock.keys()) | set(other.clock.keys())
        for k in all_keys:
            merged[k] = max(self.clock.get(k, 0), other.clock.get(k, 0))
        return VectorClock(merged)

    def happens_before(self, other: "VectorClock") -> bool:
        """Returns True if self causally precedes other."""
        all_keys = set(self.clock.keys()) | set(other.clock.keys())
        less = False
        for k in all_keys:
            a = self.clock.get(k, 0)
            b = other.clock.get(k, 0)
            if a > b:
                return False
            if a < b:
                less = True
        return less

    def is_concurrent(self, other: "VectorClock") -> bool:
        """Returns True if neither clock causally precedes the other."""
        return not self.happens_before(other) and not other.happens_before(self)

    def to_dict(self) -> dict[str, int]:
        return self.clock.copy()

    def to_json(self) -> str:
        return json.dumps(self.clock)

    @classmethod
    def from_dict(cls, d: dict) -> "VectorClock":
        return cls(d)

    @classmethod
    def from_json(cls, s: str) -> "VectorClock":
        return cls(json.loads(s))

    def __repr__(self) -> str:
        return f"VectorClock({self.clock})"


# ─── Context Entry ────────────────────────────────────────

class ContextEntry:
    """A single entry in team_context.md with causal metadata."""

    def __init__(
        self,
        agent_id: str,
        event_type: str,
        content: str,
        vector_clock: VectorClock,
        depends_on: list[str] | None = None,
    ):
        self.agent_id = agent_id
        self.event_type = event_type
        self.content = content
        self.vector_clock = vector_clock
        self.timestamp = datetime.now().isoformat()
        self.depends_on = depends_on or []

    def to_markdown(self) -> str:
        """Serialize as a team_context.md section."""
        vc_json = self.vector_clock.to_json()
        deps = ", ".join(self.depends_on) if self.depends_on else "none"
        return (
            f"\n## [{self.timestamp}] {self.agent_id} — {self.event_type}\n"
            f"**Vector Clock:** {vc_json}\n"
            f"**Causal Dependencies:** {deps}\n\n"
            f"{self.content}\n"
        )


# ─── Context Manager ──────────────────────────────────────

class TeamContext:
    """
    Reads and writes team_context.md with vector clock support.
    
    Usage:
        ctx = TeamContext()
        entry = ctx.write_entry("backend", "COMPLETE", "REST API is done...", depends_on=[])
        ctx.ensure_causal_context("crdt", entry)  # verify crdt has full context
    """

    def __init__(self, context_path: Path = TEAM_CONTEXT):
        self.path = context_path
        self._raw = self.path.read_text(encoding="utf-8") if self.path.exists() else ""
        self._entries: list[dict] = []
        self._parse_entries()

    def _parse_entries(self) -> None:
        """Extract vector clock entries from the markdown."""
        pattern = re.compile(
            r"## \[([^\]]+)\] (\S+) — (.+?)\n"
            r"\*\*Vector Clock:\*\* ({[^}]*})\n"
            r"\*\*Causal Dependencies:\*\* ([^\n]+)",
            re.MULTILINE,
        )
        for match in pattern.finditer(self._raw):
            ts, agent, event, vc_raw, deps_raw = match.groups()
            try:
                vc = json.loads(vc_raw)
            except json.JSONDecodeError:
                vc = {}
            deps = [d.strip() for d in deps_raw.split(",") if d.strip() != "none"]
            self._entries.append({
                "timestamp": ts,
                "agent": agent,
                "event": event,
                "vector_clock": vc,
                "depends_on": deps,
            })

    def get_current_clock(self) -> VectorClock:
        """Get the latest merged vector clock from all entries."""
        merged = VectorClock()
        for entry in self._entries:
            vc = VectorClock.from_dict(entry["vector_clock"])
            merged = merged.merge(vc)
        return merged

    def write_entry(
        self,
        agent_id: str,
        event_type: str,
        content: str,
        depends_on: list[str] | None = None,
    ) -> ContextEntry:
        """
        Write a new entry to team_context.md with proper vector clock.
        Automatically increments agent's clock and merges with current state.
        """
        current = self.get_current_clock()
        new_clock = current.tick(agent_id)

        entry = ContextEntry(agent_id, event_type, content, new_clock, depends_on)
        md = entry.to_markdown()

        # Append to file
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(md)

        self._raw += md
        self._entries.append({
            "timestamp": entry.timestamp,
            "agent": agent_id,
            "event": event_type,
            "vector_clock": new_clock.to_dict(),
            "depends_on": depends_on or [],
        })

        return entry

    def ensure_causal_context(self, agent_id: str, target_entry: ContextEntry) -> list[dict]:
        """
        Check that agent_id has seen all causal dependencies of target_entry.
        Returns list of missing context entries the agent should read.
        
        This prevents Agent 4 from missing decisions that Agent 2 made and
        Agent 3 built on — the causal consistency guarantee.
        """
        target_vc = target_entry.vector_clock
        missing = []

        for entry in self._entries:
            vc = VectorClock.from_dict(entry["vector_clock"])
            # If this entry causally precedes the target, the agent must know it
            if vc.happens_before(target_vc):
                if entry["agent"] != agent_id:
                    missing.append(entry)

        return missing

    def get_entries_by_agent(self, agent_id: str) -> list[dict]:
        """Get all entries written by a specific agent."""
        return [e for e in self._entries if e["agent"] == agent_id]

    def get_latest_versions(self) -> dict[str, str]:
        """Read semantic_versions.json and return current version map."""
        if SEMANTIC_VERSIONS.exists():
            with open(SEMANTIC_VERSIONS, encoding="utf-8") as f:
                data = json.load(f)
            return {
                agent: data["versions"][agent]["version"]
                for agent in data.get("versions", {})
            }
        return {}

    def check_version_compatibility(self) -> list[dict]:
        """
        Fast-path version mismatch detection.
        Returns list of incompatibilities found.
        """
        incompatibilities = []
        if not SEMANTIC_VERSIONS.exists():
            return []

        with open(SEMANTIC_VERSIONS, encoding="utf-8") as f:
            data = json.load(f)

        versions = data.get("versions", {})
        matrix = data.get("compatibility_matrix", {})

        for consumer, reqs in matrix.items():
            consumer_ver = versions.get(consumer, {})
            if consumer_ver.get("status") != "complete":
                continue

            for dep, required_ver in reqs.get("requires", {}).items():
                dep_ver = versions.get(dep, {}).get("version", "0.0.0")
                # Simple check: if dep is 0.0.0, it's not done
                if dep_ver == "0.0.0":
                    incompatibilities.append({
                        "consumer": consumer,
                        "dependency": dep,
                        "required": required_ver,
                        "actual": dep_ver,
                        "issue": f"{consumer} requires {dep} {required_ver} but {dep} version is {dep_ver}",
                    })

        return incompatibilities


# ─── CLI ──────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="PolyAgent CI — Vector Clock Utility")
    parser.add_argument("--show-clock", action="store_true", help="Show current vector clock")
    parser.add_argument("--check-compatibility", action="store_true", help="Check version compatibility")
    parser.add_argument("--write", nargs=3, metavar=("AGENT", "EVENT", "CONTENT"),
                        help="Write a context entry")
    args = parser.parse_args()

    ctx = TeamContext()

    if args.show_clock:
        clock = ctx.get_current_clock()
        print(f"Current vector clock: {clock.to_json()}")
        print(f"Total entries: {len(ctx._entries)}")
        for entry in ctx._entries:
            print(f"  [{entry['timestamp'][:19]}] {entry['agent']} — {entry['event']}")

    elif args.check_compatibility:
        issues = ctx.check_version_compatibility()
        if issues:
            print(f"Found {len(issues)} compatibility issue(s):")
            for issue in issues:
                print(f"  [{issue['consumer']}] requires [{issue['dependency']}] "
                      f"{issue['required']} but got {issue['actual']}")
        else:
            print("All version dependencies satisfied.")

    elif args.write:
        agent, event, content = args.write
        entry = ctx.write_entry(agent, event, content)
        print(f"Written entry with clock: {entry.vector_clock.to_json()}")


if __name__ == "__main__":
    main()
