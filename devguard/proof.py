"""
devguard/proof.py — Proof of Done generator.

Assembles a deterministic, serialisable ProofOfDone record from the
existing Phase 1–5 pipeline artifacts.  No new computation is performed
here — every field is read directly from the objects that were produced
by the pipeline.

No LLM is called.  No external dependencies are added.
The canonical sample_app is never touched.

Output schema:
{
  "proof_id":               str,          # UUID
  "generated_at":           str,          # ISO-8601 UTC
  "final_status":           str,          # "VERIFIED" | "BLOCKED / FAILED"

  "maintenance_request": {
    "request_id":           str,
    "description":          str,
    "requestor":            str,
  },

  "requested_behavior": {
    "target_behavior_id":   str,
    "target_symbol":        str,
    "target_file":          str,
    "from_value":           str,
    "to_value":             str,
  },

  "target_behavior":        str,          # human-readable description from contract

  "protected_behaviors": [               # one entry per protected clause
    {
      "behavior_id":        str,
      "name":               str,
      "severity":           str,
      "must_not":           str,
      "status":             str,          # "PRESERVED" | "VIOLATED"
    }
  ],

  "allowed_scope": {
    "symbol":               str,
    "file":                 str,
    "from_value":           str,
    "to_value":             str,
    "scope_note":           str,
  },

  "files_changed":          [str],        # from BobResponse.files_modified

  "test_results": {
    "tests_run":            int,
    "tests_passed":         int,
    "raw_tests_failed":     int,          # raw subprocess count (includes expected)
    "protected_tests_failed": [str],      # genuine protected-behavior failures
  },

  "intent_drift": {
    "drift_detected":       bool,
    "status":               str,          # "CLEAR" | "DRIFT_DETECTED"
    "unintended_changes":   [str],        # symbol names
    "protected_violations": int,          # count
  },

  "protected_behavior_status":  str,      # "PRESERVED" | "VIOLATED"
  "unexpected_changes":         [str],    # symbol names
  "contract_satisfied":         bool,
  "verification_summary":       str,
}
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from devguard.contract import BehavioralContract, MaintenanceRequest
from devguard.bob_executor import BobResponse
from devguard.drift_detector import DriftResult
from devguard.verifier import VerificationResult


# ---------------------------------------------------------------------------
# ProofOfDone
# ---------------------------------------------------------------------------

class ProofOfDone:
    """An immutable, serialisable Proof of Done record."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def to_dict(self) -> dict:
        return self._data

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self._data, indent=indent)

    def save(self, path: str | Path) -> Path:
        """Write the proof as a JSON file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json(), encoding="utf-8")
        return p

    @property
    def final_status(self) -> str:
        return self._data["final_status"]

    @property
    def contract_satisfied(self) -> bool:
        return self._data["contract_satisfied"]

    @property
    def proof_id(self) -> str:
        return self._data["proof_id"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_proof(
    request: MaintenanceRequest,
    contract: BehavioralContract,
    response: BobResponse,
    drift: DriftResult,
    verification: VerificationResult,
) -> ProofOfDone:
    """Assemble a Proof of Done from the Phase 1–5 pipeline artifacts.

    Every field is read directly from the supplied objects.
    No values are invented, inferred from LLM output, or hardcoded.

    Args:
        request:      The original maintenance request.
        contract:     The behavioral contract governing the request.
        response:     Bob's proposed change (BobResponse).
        drift:        The intent drift analysis result.
        verification: The behavioral verification result.

    Returns:
        A ProofOfDone with final_status "VERIFIED" or "BLOCKED / FAILED".
    """
    # --- Final status — derived solely from verification.contract_satisfied ---
    final_status = "VERIFIED" if verification.contract_satisfied else "BLOCKED / FAILED"

    # --- Maintenance request summary ---
    maintenance_request = {
        "request_id":  request.request_id,
        "description": request.description,
        "requestor":   request.requestor,
    }

    # --- Requested behavior (the precise scope of the change) ---
    allowed = contract.allowed_change
    requested_behavior = {
        "target_behavior_id": request.target_behavior_id,
        "target_symbol":      request.target_symbol,
        "target_file":        request.target_file,
        "from_value":         allowed["from_value"],
        "to_value":           allowed["to_value"],
    }

    # --- Target behavior (human-readable description from the contract) ---
    target_behavior = contract.to_dict().get("target_behavior", {}).get("description", "")

    # --- Protected behaviors — one entry per clause, with PRESERVED / VIOLATED ---
    violated_behaviors = {
        v["behavior_id"]
        for v in drift.protected_violations
    }
    # Also flag any behavior whose test anchors appear in protected_tests_failed
    failed_fns = {tid.split("::")[-1] for tid in verification.protected_tests_failed}
    for clause in contract.protected_clauses:
        anchors = set(clause.get("test_anchors", []))
        if anchors & failed_fns:
            violated_behaviors.add(clause["behavior_id"])

    protected_behaviors = [
        {
            "behavior_id": clause["behavior_id"],
            "name":        clause["name"],
            "severity":    clause["severity"],
            "must_not":    clause["must_not"],
            "status":      "VIOLATED" if clause["behavior_id"] in violated_behaviors
                           else "PRESERVED",
        }
        for clause in contract.protected_clauses
    ]

    # --- Allowed scope ---
    allowed_scope = {
        "symbol":     allowed["symbol"],
        "file":       allowed["file"],
        "from_value": allowed["from_value"],
        "to_value":   allowed["to_value"],
        "scope_note": allowed["scope_note"],
    }

    # --- Files changed (from Bob's response) ---
    files_changed = list(response.files_modified)

    # --- Test results (from verification) ---
    vd = verification.to_dict()
    test_results = {
        "tests_run":               vd["tests_run"],
        "tests_passed":            vd["tests_passed"],
        "raw_tests_failed":        vd["tests_failed"],
        "protected_tests_failed":  vd["protected_tests_failed"],
    }

    # --- Intent drift summary ---
    dd = drift.to_dict()
    intent_drift = {
        "drift_detected":      dd["drift_detected"],
        "status":              dd["status"],
        "unintended_changes":  [u["symbol"] for u in drift.unintended_changes],
        "protected_violations": len(drift.protected_violations),
    }

    # --- Overall protected behavior status ---
    protected_behavior_status = (
        "VIOLATED" if not verification.protected_behavior_preserved else "PRESERVED"
    )

    return ProofOfDone({
        "proof_id":                  str(uuid.uuid4()),
        "generated_at":              datetime.now(timezone.utc).isoformat(),
        "final_status":              final_status,
        "maintenance_request":       maintenance_request,
        "requested_behavior":        requested_behavior,
        "target_behavior":           target_behavior,
        "protected_behaviors":       protected_behaviors,
        "allowed_scope":             allowed_scope,
        "files_changed":             files_changed,
        "test_results":              test_results,
        "intent_drift":              intent_drift,
        "protected_behavior_status": protected_behavior_status,
        "unexpected_changes":        vd["unexpected_changes"],
        "contract_satisfied":        vd["contract_satisfied"],
        "verification_summary":      vd["summary"],
    })
