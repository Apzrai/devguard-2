"""
test_proof.py — Tests for devguard/proof.py (Phase 6)

Covers:
  - ProofOfDone structure and required fields
  - final_status derived from actual verification result ("VERIFIED" / "BLOCKED / FAILED")
  - successful corrected-change proof
  - controlled-failure blocked proof
  - protected behavior status per clause
  - intent drift fields
  - evidence/provenance preservation (no fabricated values)
  - serialisation
"""

import json
import uuid
import pytest
from pathlib import Path

from devguard.understand import understand
from devguard.behavior_map import build_behavior_map
from devguard.evidence import collect_evidence
from devguard.contract import build_contract, make_enterprise_discount_request
from devguard.impact import analyze_impact
from devguard.bob_task import build_bob_task
from devguard.bob_executor import MockBobExecutor
from devguard.drift_detector import detect_drift
from devguard.verifier import verify
from devguard.proof import ProofOfDone, build_proof

SAMPLE_APP = Path(__file__).parent.parent.parent / "sample_app"

REQUIRED_FIELDS = [
    "proof_id",
    "generated_at",
    "final_status",
    "maintenance_request",
    "requested_behavior",
    "target_behavior",
    "protected_behaviors",
    "allowed_scope",
    "files_changed",
    "test_results",
    "intent_drift",
    "protected_behavior_status",
    "unexpected_changes",
    "contract_satisfied",
    "verification_summary",
]


# ---------------------------------------------------------------------------
# Shared fixtures — build full pipeline once per module
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pipeline():
    u = understand(SAMPLE_APP)
    bmap = build_behavior_map(u)
    ev = collect_evidence(u)
    request = make_enterprise_discount_request()
    contract = build_contract(bmap, request)
    impact = analyze_impact(u, bmap, contract)
    task = build_bob_task(u, bmap, ev, contract, impact, request)
    return {
        "request": request,
        "contract": contract,
        "task": task,
    }


@pytest.fixture(scope="module")
def proof_success(pipeline):
    """Proof for the corrected Enterprise-only change."""
    response = MockBobExecutor(scenario="success").execute(pipeline["task"])
    drift = detect_drift(pipeline["contract"], response)
    verification = verify(pipeline["contract"], response, drift, SAMPLE_APP)
    return build_proof(
        pipeline["request"],
        pipeline["contract"],
        response,
        drift,
        verification,
    )


@pytest.fixture(scope="module")
def proof_failure(pipeline):
    """Proof for the controlled-failure scenario (Loyalty also changed)."""
    response = MockBobExecutor(scenario="failure").execute(pipeline["task"])
    drift = detect_drift(pipeline["contract"], response)
    verification = verify(pipeline["contract"], response, drift, SAMPLE_APP)
    return build_proof(
        pipeline["request"],
        pipeline["contract"],
        response,
        drift,
        verification,
    )


# ---------------------------------------------------------------------------
# ProofOfDone type
# ---------------------------------------------------------------------------

class TestProofOfDoneType:
    def test_returns_proof_of_done_instance(self, proof_success):
        assert isinstance(proof_success, ProofOfDone)

    def test_proof_id_is_uuid(self, proof_success):
        uuid.UUID(proof_success.proof_id)  # must not raise

    def test_to_dict_returns_dict(self, proof_success):
        assert isinstance(proof_success.to_dict(), dict)

    def test_to_json_is_valid_json(self, proof_success):
        parsed = json.loads(proof_success.to_json())
        assert isinstance(parsed, dict)

    def test_save_writes_file(self, proof_success, tmp_path):
        out = tmp_path / "proof.json"
        proof_success.save(out)
        assert out.exists()
        parsed = json.loads(out.read_text(encoding="utf-8"))
        assert "final_status" in parsed


# ---------------------------------------------------------------------------
# Required fields
# ---------------------------------------------------------------------------

class TestRequiredFields:
    def test_all_required_fields_present_success(self, proof_success):
        d = proof_success.to_dict()
        for field in REQUIRED_FIELDS:
            assert field in d, f"Missing required field: {field}"

    def test_all_required_fields_present_failure(self, proof_failure):
        d = proof_failure.to_dict()
        for field in REQUIRED_FIELDS:
            assert field in d, f"Missing required field: {field}"

    def test_maintenance_request_has_subfields(self, proof_success):
        mr = proof_success.to_dict()["maintenance_request"]
        assert "request_id" in mr
        assert "description" in mr
        assert "requestor" in mr

    def test_requested_behavior_has_subfields(self, proof_success):
        rb = proof_success.to_dict()["requested_behavior"]
        for key in ["target_behavior_id", "target_symbol", "target_file",
                    "from_value", "to_value"]:
            assert key in rb, f"Missing key in requested_behavior: {key}"

    def test_allowed_scope_has_subfields(self, proof_success):
        sc = proof_success.to_dict()["allowed_scope"]
        for key in ["symbol", "file", "from_value", "to_value", "scope_note"]:
            assert key in sc, f"Missing key in allowed_scope: {key}"

    def test_test_results_has_subfields(self, proof_success):
        tr = proof_success.to_dict()["test_results"]
        for key in ["tests_run", "tests_passed", "raw_tests_failed",
                    "protected_tests_failed"]:
            assert key in tr, f"Missing key in test_results: {key}"

    def test_intent_drift_has_subfields(self, proof_success):
        id_ = proof_success.to_dict()["intent_drift"]
        for key in ["drift_detected", "status", "unintended_changes",
                    "protected_violations"]:
            assert key in id_, f"Missing key in intent_drift: {key}"


# ---------------------------------------------------------------------------
# Successful proof — VERIFIED
# ---------------------------------------------------------------------------

class TestProofSuccess:
    def test_final_status_is_verified(self, proof_success):
        assert proof_success.final_status == "VERIFIED"

    def test_contract_satisfied_is_true(self, proof_success):
        assert proof_success.contract_satisfied is True

    def test_protected_behavior_status_is_preserved(self, proof_success):
        assert proof_success.to_dict()["protected_behavior_status"] == "PRESERVED"

    def test_no_unexpected_changes(self, proof_success):
        assert proof_success.to_dict()["unexpected_changes"] == []

    def test_no_unintended_changes_in_drift(self, proof_success):
        assert proof_success.to_dict()["intent_drift"]["unintended_changes"] == []

    def test_drift_not_detected(self, proof_success):
        assert proof_success.to_dict()["intent_drift"]["drift_detected"] is False

    def test_drift_status_is_clear(self, proof_success):
        assert proof_success.to_dict()["intent_drift"]["status"] == "CLEAR"

    def test_no_protected_violations(self, proof_success):
        assert proof_success.to_dict()["intent_drift"]["protected_violations"] == 0

    def test_all_protected_behaviors_preserved(self, proof_success):
        for clause in proof_success.to_dict()["protected_behaviors"]:
            assert clause["status"] == "PRESERVED", (
                f"Clause {clause['behavior_id']} ({clause['name']}) "
                f"unexpectedly VIOLATED in success proof"
            )

    def test_files_changed_includes_customers(self, proof_success):
        assert any("customers" in f for f in proof_success.to_dict()["files_changed"])

    def test_test_results_run_is_positive(self, proof_success):
        assert proof_success.to_dict()["test_results"]["tests_run"] > 0

    def test_no_protected_tests_failed(self, proof_success):
        assert proof_success.to_dict()["test_results"]["protected_tests_failed"] == []

    def test_target_symbol_is_enterprise_discount(self, proof_success):
        assert proof_success.to_dict()["requested_behavior"]["target_symbol"] == "ENTERPRISE_DISCOUNT"

    def test_to_value_is_015(self, proof_success):
        assert proof_success.to_dict()["requested_behavior"]["to_value"] == "0.15"

    def test_verification_summary_contains_passed(self, proof_success):
        summary = proof_success.to_dict()["verification_summary"]
        assert "PASSED" in summary or "passed" in summary

    def test_target_behavior_is_non_empty(self, proof_success):
        assert proof_success.to_dict()["target_behavior"] != ""


# ---------------------------------------------------------------------------
# Failure proof — BLOCKED / FAILED
# ---------------------------------------------------------------------------

class TestProofFailure:
    def test_final_status_is_blocked(self, proof_failure):
        assert proof_failure.final_status == "BLOCKED / FAILED"

    def test_contract_satisfied_is_false(self, proof_failure):
        assert proof_failure.contract_satisfied is False

    def test_protected_behavior_status_is_violated(self, proof_failure):
        assert proof_failure.to_dict()["protected_behavior_status"] == "VIOLATED"

    def test_loyalty_in_unexpected_changes(self, proof_failure):
        assert "LOYALTY_DISCOUNT" in proof_failure.to_dict()["unexpected_changes"]

    def test_drift_detected(self, proof_failure):
        assert proof_failure.to_dict()["intent_drift"]["drift_detected"] is True

    def test_drift_status_is_drift_detected(self, proof_failure):
        assert proof_failure.to_dict()["intent_drift"]["status"] == "DRIFT_DETECTED"

    def test_loyalty_in_unintended_changes(self, proof_failure):
        assert "LOYALTY_DISCOUNT" in proof_failure.to_dict()["intent_drift"]["unintended_changes"]

    def test_protected_violations_count_positive(self, proof_failure):
        assert proof_failure.to_dict()["intent_drift"]["protected_violations"] >= 1

    def test_at_least_one_protected_behavior_violated(self, proof_failure):
        clauses = proof_failure.to_dict()["protected_behaviors"]
        violated = [c for c in clauses if c["status"] == "VIOLATED"]
        assert len(violated) >= 1

    def test_loyalty_clause_is_violated(self, proof_failure):
        clauses = proof_failure.to_dict()["protected_behaviors"]
        loyalty = next((c for c in clauses if c["behavior_id"] == "B002"), None)
        assert loyalty is not None
        assert loyalty["status"] == "VIOLATED"

    def test_verification_summary_contains_failed(self, proof_failure):
        summary = proof_failure.to_dict()["verification_summary"]
        assert "FAILED" in summary or "failed" in summary


# ---------------------------------------------------------------------------
# Status derived from verification — not hardcoded
# ---------------------------------------------------------------------------

class TestStatusDerivation:
    def test_verified_status_matches_contract_satisfied(self, proof_success):
        d = proof_success.to_dict()
        assert (d["final_status"] == "VERIFIED") == d["contract_satisfied"]

    def test_blocked_status_matches_contract_not_satisfied(self, proof_failure):
        d = proof_failure.to_dict()
        assert (d["final_status"] == "BLOCKED / FAILED") == (not d["contract_satisfied"])

    def test_two_proofs_have_different_statuses(self, proof_success, proof_failure):
        assert proof_success.final_status != proof_failure.final_status

    def test_two_proofs_have_different_ids(self, proof_success, proof_failure):
        assert proof_success.proof_id != proof_failure.proof_id


# ---------------------------------------------------------------------------
# Provenance preservation
# ---------------------------------------------------------------------------

class TestProvenancePreservation:
    def test_request_id_matches_original(self, pipeline, proof_success):
        assert (
            proof_success.to_dict()["maintenance_request"]["request_id"]
            == pipeline["request"].request_id
        )

    def test_description_matches_original(self, pipeline, proof_success):
        assert (
            proof_success.to_dict()["maintenance_request"]["description"]
            == pipeline["request"].description
        )

    def test_allowed_symbol_matches_contract(self, pipeline, proof_success):
        assert (
            proof_success.to_dict()["allowed_scope"]["symbol"]
            == pipeline["contract"].allowed_change["symbol"]
        )

    def test_canonical_sample_app_unchanged(self):
        from sample_app.customers import (
            ENTERPRISE_DISCOUNT, LOYALTY_DISCOUNT, NEW_CUSTOMER_DISCOUNT,
        )
        assert ENTERPRISE_DISCOUNT == pytest.approx(0.10)
        assert LOYALTY_DISCOUNT == pytest.approx(0.10)
        assert NEW_CUSTOMER_DISCOUNT == pytest.approx(0.05)
