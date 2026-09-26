"""
devguard/bob_task.py — Bob-ready maintenance task builder.

Assembles everything DEVGUARD has produced into a single structured
BobTask that can be handed to IBM Bob for execution.

A BobTask is a self-contained, serialisable package containing:
  - The maintenance request (what to do)
  - Current behavior snapshot (what exists now)
  - Evidence record (provenance hash of the project state)
  - Behavioral contract (what is protected, what may change)
  - Impact analysis (which files/tests are at risk)
  - Exact file context (the file Bob must edit, with its current content)
  - Allowed scope (precisely scoped change instruction)
  - Success criteria (how to know the task is done)
  - A human-readable prompt ready to paste into the IBM Bob Agent interface

The BobTask is the boundary between DEVGUARD and Bob.
DEVGUARD stops here.  Bob takes over.

No LLM is called in this module.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from devguard.behavior_map import BehaviorMap
from devguard.contract import BehavioralContract, MaintenanceRequest
from devguard.evidence import Evidence
from devguard.impact import ImpactAnalysis
from devguard.understand import ProjectUnderstanding


# ---------------------------------------------------------------------------
# BobTask data model
# ---------------------------------------------------------------------------

@dataclass
class BobTask:
    """A fully-assembled, Bob-ready maintenance task.

    This is the structured handoff package that DEVGUARD passes to Bob.
    It is immutable once created — Bob receives it as a read-only brief.
    """

    task_id: str
    created_at: str
    title: str

    # Pipeline artifacts (serialisable dicts)
    maintenance_request: dict
    current_behavior: dict        # behavior_id -> description for affected behavior
    evidence_summary: dict        # aggregate_hash + file count + timestamp
    contract: dict                # full behavioral contract
    impact: dict                  # impact analysis summary
    file_context: dict            # the actual file(s) Bob must edit
    allowed_scope: dict           # precisely: symbol, file, from_value, to_value
    protected_behaviors: list     # clauses Bob must not violate
    success_criteria: list        # ordered acceptance criteria

    # The ready-to-use prompt for the IBM Bob Agent interface
    bob_prompt: str

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "created_at": self.created_at,
            "title": self.title,
            "maintenance_request": self.maintenance_request,
            "current_behavior": self.current_behavior,
            "evidence_summary": self.evidence_summary,
            "contract": self.contract,
            "impact": self.impact,
            "file_context": self.file_context,
            "allowed_scope": self.allowed_scope,
            "protected_behaviors": self.protected_behaviors,
            "success_criteria": self.success_criteria,
            "bob_prompt": self.bob_prompt,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: str | Path) -> Path:
        """Write the BobTask as a JSON file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json(), encoding="utf-8")
        return p


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_bob_prompt(
    request: MaintenanceRequest,
    contract: BehavioralContract,
    file_context: dict,
    impact: ImpactAnalysis,
) -> str:
    """Build the human-readable prompt for the IBM Bob Agent interface.

    This prompt is complete and self-contained — a developer can paste it
    directly into the IBM Bob Agent chat interface without any additional
    context.
    """
    allowed = contract.allowed_change
    protected = contract.protected_clauses

    # Collect the high-risk tests so Bob is aware of what will catch violations
    high_risk = [
        t for t in impact.at_risk_tests if t["risk_level"] == "HIGH"
    ]
    high_risk_fns = ", ".join(t["test_function"] for t in high_risk[:6])
    if len(high_risk) > 6:
        high_risk_fns += f" (and {len(high_risk) - 6} more)"

    protected_summary = "\n".join(
        f"  - [{c['severity']}] {c['name']}: {c['must_not']}"
        for c in protected
        if c["severity"] in ("CRITICAL", "HIGH")
    )

    criteria = "\n".join(
        f"  {i+1}. {c}" for i, c in enumerate(contract.success_criteria)
    )

    file_path = file_context.get("relative_path", allowed["file"])
    current_val = allowed["from_value"]
    new_val = allowed["to_value"]
    symbol = allowed["symbol"]

    prompt = f"""You are acting as a precise software engineering agent.

TASK
----
{request.description}

ALLOWED CHANGE — EXACTLY ONE SYMBOL IN ONE FILE
------------------------------------------------
File   : {file_path}
Symbol : {symbol}
Change : {current_val}  ->  {new_val}

You must change ONLY the line that sets `{symbol} = {current_val}` to `{symbol} = {new_val}`.
No other line, file, or symbol may be modified.

CURRENT FILE CONTENT
--------------------
{file_context.get('content', '(see file on disk)')}

PROTECTED BEHAVIORS — DO NOT VIOLATE
--------------------------------------
{protected_summary}

The following tests WILL FAIL if you modify anything beyond the allowed scope.
These failures mean you have violated a protected behavior:
  {high_risk_fns}

SUCCESS CRITERIA
----------------
{criteria}

INSTRUCTIONS
------------
1. Open the file: {file_path}
2. Find the line:   {symbol}: float = {current_val}
3. Change it to:    {symbol}: float = {new_val}
4. Save the file.
5. Run the test suite: pytest sample_app/tests/
6. Confirm all tests pass.
7. Report back: which line was changed, what the diff is, and the test result.

Do not make any other changes. Do not refactor. Do not add comments.
This change is complete when — and only when — all tests pass and only
`{symbol}` has been modified.
"""
    return prompt.strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_bob_task(
    u: ProjectUnderstanding,
    bmap: BehaviorMap,
    ev: Evidence,
    contract: BehavioralContract,
    impact: ImpactAnalysis,
    request: MaintenanceRequest,
) -> BobTask:
    """Assemble a BobTask from all DEVGUARD pipeline artifacts.

    Reads the content of the file Bob must edit so the prompt is
    fully self-contained.

    Args:
        u:        ProjectUnderstanding of the target project.
        bmap:     BehaviorMap for the project.
        ev:       Evidence record (pre-change provenance).
        contract: Behavioral contract for the maintenance request.
        impact:   Impact analysis results.
        request:  The maintenance request.

    Returns:
        A BobTask ready to hand to IBM Bob.
    """
    allowed = contract.allowed_change
    target_file_name = allowed["file"]       # e.g. "customers.py"
    project_root = Path(u.to_dict()["project_root"])

    # Locate the file Bob must edit
    target_abs = project_root / target_file_name
    if not target_abs.exists():
        # Try a recursive search within the project root
        candidates = list(project_root.rglob(target_file_name))
        target_abs = candidates[0] if candidates else target_abs

    relative_path = str(target_abs.relative_to(project_root.parent))
    file_content = target_abs.read_text(encoding="utf-8") if target_abs.exists() else "(file not found)"

    file_context = {
        "relative_path": relative_path,
        "absolute_path": str(target_abs),
        "sha256": ev.get_hash(target_file_name) or "(unknown)",
        "content": file_content,
    }

    # Current behavior snapshot — just the targeted behavior
    target_b = bmap.get(request.target_behavior_id)
    current_behavior = {
        request.target_behavior_id: target_b["description"] if target_b else ""
    }

    # Evidence summary (not the full hash list — just the fingerprint)
    ev_data = ev.to_dict()
    evidence_summary = {
        "evidence_id": ev_data["evidence_id"],
        "recorded_at": ev_data["recorded_at"],
        "aggregate_hash": ev_data["aggregate_hash"],
        "total_files": ev_data["total_files"],
        "total_test_functions": ev_data["total_test_functions"],
    }

    # Impact summary (omit the raw test list to keep the task compact)
    impact_data = impact.to_dict()
    impact_summary = {
        "impact_id": impact_data["impact_id"],
        "directly_affected": [d["file"] for d in impact_data["directly_affected"]],
        "indirectly_affected": [d["file"] for d in impact_data["indirectly_affected"]],
        "at_risk_test_count": len(impact_data["at_risk_tests"]),
        "high_risk_test_count": sum(
            1 for t in impact_data["at_risk_tests"] if t["risk_level"] == "HIGH"
        ),
        "safe_to_change": impact_data["safe_to_change"],
        "risk_summary": impact_data["risk_summary"],
    }

    bob_prompt = _build_bob_prompt(request, contract, file_context, impact)

    return BobTask(
        task_id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc).isoformat(),
        title=request.description,
        maintenance_request=request.to_dict(),
        current_behavior=current_behavior,
        evidence_summary=evidence_summary,
        contract=contract.to_dict(),
        impact=impact_summary,
        file_context=file_context,
        allowed_scope=allowed,
        protected_behaviors=contract.protected_clauses,
        success_criteria=contract.success_criteria,
        bob_prompt=bob_prompt,
    )
