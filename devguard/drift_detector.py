"""
devguard/drift_detector.py — Intent Drift Detector.

Compares the proposed change (from Bob's response) against the behavioral
contract to determine whether the actual change matches the developer's
original maintenance request.

Intent drift is detected when a proposed diff or set of file modifications
touches symbols, files, or behaviors that are:
  - Outside the allowed scope (only the allowed_change.symbol in allowed_change.file)
  - Protected by a contract clause

No LLM is called.  Drift is detected deterministically by:
  1. Parsing the unified diff to extract changed symbols.
  2. Comparing changed symbols against the contract's allowed_change.
  3. Checking each changed symbol against protected clause source_symbols.

Output schema:
{
  "drift_id": str,
  "detected_at": str,
  "contract_id": str,
  "allowed_symbol": str,
  "allowed_file": str,
  "drift_detected": bool,
  "intended_changes": [DriftItem],   # changes that match the request
  "unintended_changes": [DriftItem], # changes outside the allowed scope
  "protected_violations": [ProtectedViolation],
  "status": "CLEAR" | "DRIFT_DETECTED",
  "summary": str,
}

DriftItem:
{
  "symbol": str,
  "file": str,
  "from_value": str | None,
  "to_value": str | None,
  "is_allowed": bool,
  "provenance": str,    # "DIFF_ANALYSIS"
}

ProtectedViolation:
{
  "behavior_id": str,
  "behavior_name": str,
  "source_symbol": str,
  "must_not": str,
  "severity": str,
  "changed_symbol": str,
  "evidence": str,       # the diff line that shows the violation
}
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from devguard.contract import BehavioralContract
from devguard.bob_executor import BobResponse


# ---------------------------------------------------------------------------
# Diff parsing helpers
# ---------------------------------------------------------------------------

# Matches annotated-assignment constants:  NAME: float = VALUE
# or plain assignments:                    NAME = VALUE
_ASSIGN_RE = re.compile(
    r'^[-+]\s*([A-Z_][A-Z0-9_]*)\s*(?::\s*\S+)?\s*=\s*([^\s#]+)'
)


def _parse_diff_changes(diff: str) -> list[dict]:
    """Extract symbol changes from a unified diff string.

    For each line that starts with '+' or '-' (excluding the file header
    lines '---'/'+++'), attempt to parse it as a constant assignment.

    Returns a list of dicts:
      {
        "symbol":    str,
        "sign":      "+" | "-",
        "value":     str,
        "raw_line":  str,
      }
    """
    changes: list[dict] = []
    for line in diff.splitlines():
        # Skip unified diff headers
        if line.startswith("---") or line.startswith("+++") or line.startswith("@@"):
            continue
        if not line.startswith("+") and not line.startswith("-"):
            continue
        sign = line[0]
        m = _ASSIGN_RE.match(line)
        if m:
            symbol = m.group(1)
            value = m.group(2).rstrip(",;")
            changes.append({
                "symbol": symbol,
                "sign": sign,
                "value": value,
                "raw_line": line,
            })
    return changes


def _correlate_changes(raw: list[dict]) -> list[dict]:
    """Pair removed (-) and added (+) lines for the same symbol.

    Returns a list of dicts:
      {
        "symbol": str,
        "from_value": str | None,
        "to_value": str | None,
        "raw_removed": str | None,
        "raw_added":   str | None,
      }
    """
    removed: dict[str, dict] = {}
    added: dict[str, dict] = {}
    for c in raw:
        if c["sign"] == "-":
            removed[c["symbol"]] = c
        else:
            added[c["symbol"]] = c

    all_symbols = set(removed) | set(added)
    result: list[dict] = []
    for sym in sorted(all_symbols):
        result.append({
            "symbol": sym,
            "from_value": removed[sym]["value"] if sym in removed else None,
            "to_value": added[sym]["value"] if sym in added else None,
            "raw_removed": removed[sym]["raw_line"] if sym in removed else None,
            "raw_added": added[sym]["raw_line"] if sym in added else None,
        })
    return result


# ---------------------------------------------------------------------------
# Drift detection result
# ---------------------------------------------------------------------------

class DriftResult:
    """The result of an intent drift analysis."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def to_dict(self) -> dict:
        return self._data

    @property
    def drift_detected(self) -> bool:
        return self._data["drift_detected"]

    @property
    def status(self) -> str:
        return self._data["status"]

    @property
    def intended_changes(self) -> list[dict]:
        return self._data["intended_changes"]

    @property
    def unintended_changes(self) -> list[dict]:
        return self._data["unintended_changes"]

    @property
    def protected_violations(self) -> list[dict]:
        return self._data["protected_violations"]

    @property
    def summary(self) -> str:
        return self._data["summary"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_drift(
    contract: BehavioralContract,
    response: BobResponse,
) -> DriftResult:
    """Detect intent drift by comparing the proposed diff against the contract.

    Steps:
      1. Parse the unified diff from the BobResponse.
      2. For each changed symbol, determine if it is within the allowed scope.
      3. For each out-of-scope change, check whether it violates a protected clause.

    Args:
        contract: The BehavioralContract governing the maintenance request.
        response: Bob's BobResponse containing the proposed diff.

    Returns:
        A DriftResult with full analysis of intended vs. unintended changes.
    """
    allowed = contract.allowed_change
    allowed_symbol = allowed["symbol"]   # e.g. "ENTERPRISE_DISCOUNT"
    allowed_file = allowed["file"]       # e.g. "customers.py"
    allowed_from = allowed["from_value"]
    allowed_to = allowed["to_value"]

    # Parse the diff
    raw_changes = _parse_diff_changes(response.proposed_diff)
    correlated = _correlate_changes(raw_changes)

    # Classify each changed symbol
    intended_changes: list[dict] = []
    unintended_changes: list[dict] = []

    for ch in correlated:
        sym = ch["symbol"]
        is_allowed = (sym == allowed_symbol)
        item = {
            "symbol": sym,
            "file": allowed_file,   # all changes are in the same file for this scenario
            "from_value": ch["from_value"],
            "to_value": ch["to_value"],
            "is_allowed": is_allowed,
            "provenance": "DIFF_ANALYSIS",
        }
        if is_allowed:
            intended_changes.append(item)
        else:
            unintended_changes.append(item)

    # For each unintended change, check whether it violates a protected clause
    protected_violations: list[dict] = []
    for uch in unintended_changes:
        for clause in contract.protected_clauses:
            # clause["source_symbol"] may be a comma-separated list
            clause_symbols = [
                s.strip()
                for s in clause.get("source_symbol", "").split(",")
            ]
            if uch["symbol"] in clause_symbols:
                # Find the raw diff line as evidence
                evidence_line = ""
                for raw in raw_changes:
                    if raw["symbol"] == uch["symbol"] and raw["sign"] == "+":
                        evidence_line = raw["raw_line"]
                        break

                protected_violations.append({
                    "behavior_id": clause["behavior_id"],
                    "behavior_name": clause["name"],
                    "source_symbol": uch["symbol"],
                    "must_not": clause["must_not"],
                    "severity": clause["severity"],
                    "changed_symbol": uch["symbol"],
                    "from_value": uch["from_value"],
                    "to_value": uch["to_value"],
                    "evidence": evidence_line,
                })
                break  # one violation record per unintended change

    # Verify intended change is actually correct
    intended_correct = False
    for ich in intended_changes:
        if (
            ich["symbol"] == allowed_symbol
            and ich["to_value"] is not None
            and allowed_to in ich["to_value"]
        ):
            intended_correct = True
            break

    drift_detected = len(unintended_changes) > 0 or len(protected_violations) > 0
    status = "DRIFT_DETECTED" if drift_detected else "CLEAR"

    # Build human-readable summary
    if drift_detected:
        violation_lines = []
        for v in protected_violations:
            violation_lines.append(
                f"  [{v['severity']}] {v['source_symbol']}: "
                f"{v['from_value']} → {v['to_value']} "
                f"(protected by clause {v['behavior_id']}: {v['behavior_name']})"
            )
        unintended_lines = []
        for uch in unintended_changes:
            unintended_lines.append(
                f"  {uch['symbol']}: {uch['from_value']} → {uch['to_value']}"
            )
        summary = (
            f"INTENT DRIFT DETECTED\n\n"
            f"Requested: {allowed_symbol} {allowed_from} → {allowed_to}\n\n"
            f"Unintended changes ({len(unintended_changes)}):\n"
            + "\n".join(unintended_lines)
            + (
                f"\n\nProtected behavior violations ({len(protected_violations)}):\n"
                + "\n".join(violation_lines)
                if protected_violations else ""
            )
            + f"\n\nStatus: BLOCKED / FAILED"
        )
    else:
        summary = (
            f"No intent drift detected. "
            f"Only {allowed_symbol} was changed ({allowed_from} → {allowed_to}). "
            f"All protected behaviors preserved. "
            f"Status: CLEAR"
        )

    return DriftResult({
        "drift_id": str(uuid.uuid4()),
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "contract_id": contract.contract_id,
        "allowed_symbol": allowed_symbol,
        "allowed_file": allowed_file,
        "drift_detected": drift_detected,
        "intended_correct": intended_correct,
        "intended_changes": intended_changes,
        "unintended_changes": unintended_changes,
        "protected_violations": protected_violations,
        "status": status,
        "summary": summary,
    })
