"""
test_drift_detector.py — Tests for devguard/drift_detector.py

Covers:
  - Diff parsing (symbol extraction from unified diff)
  - Drift detection on the failure scenario (Loyalty also changed)
  - No drift on the success scenario (only Enterprise changed)
  - Protected behavior identification
  - DriftResult structure and serialisation
"""

import json
import pytest
from pathlib import Path

from devguard.understand import understand
from devguard.behavior_map import build_behavior_map
from devguard.contract import build_contract, make_enterprise_discount_request
from devguard.bob_executor import MockBobExecutor
from devguard.bob_task import build_bob_task
from devguard.evidence import collect_evidence
from devguard.impact import analyze_impact
from devguard.drift_detector import (
    detect_drift,
    DriftResult,
    _parse_diff_changes,
    _correlate_changes,
)

SAMPLE_APP = Path(__file__).parent.parent.parent / "sample_app"


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pipeline():
    """Build the full DEVGUARD pipeline once for all tests."""
    u = understand(SAMPLE_APP)
    bmap = build_behavior_map(u)
    ev = collect_evidence(u)
    request = make_enterprise_discount_request()
    contract = build_contract(bmap, request)
    impact = analyze_impact(u, bmap, contract)
    task = build_bob_task(u, bmap, ev, contract, impact, request)
    return {"u": u, "bmap": bmap, "ev": ev, "request": request,
            "contract": contract, "impact": impact, "task": task}


@pytest.fixture(scope="module")
def bad_response(pipeline):
    """Bob's failure response — also changes LOYALTY_DISCOUNT."""
    return MockBobExecutor(scenario="failure").execute(pipeline["task"])


@pytest.fixture(scope="module")
def good_response(pipeline):
    """Bob's success response — only changes ENTERPRISE_DISCOUNT."""
    return MockBobExecutor(scenario="success").execute(pipeline["task"])


@pytest.fixture(scope="module")
def drift_failure(pipeline, bad_response):
    """DriftResult for the controlled failure scenario."""
    return detect_drift(pipeline["contract"], bad_response)


@pytest.fixture(scope="module")
def drift_success(pipeline, good_response):
    """DriftResult for the corrected success scenario."""
    return detect_drift(pipeline["contract"], good_response)


# ---------------------------------------------------------------------------
# Diff parsing unit tests
# ---------------------------------------------------------------------------

class TestParseDiffChanges:
    def test_parses_removed_constant(self):
        diff = "-LOYALTY_DISCOUNT: float = 0.10               # 10%\n"
        changes = _parse_diff_changes(diff)
        assert any(c["symbol"] == "LOYALTY_DISCOUNT" and c["sign"] == "-" for c in changes)

    def test_parses_added_constant(self):
        diff = "+LOYALTY_DISCOUNT: float = 0.15               # 15%\n"
        changes = _parse_diff_changes(diff)
        assert any(c["symbol"] == "LOYALTY_DISCOUNT" and c["sign"] == "+" for c in changes)

    def test_skips_file_headers(self):
        diff = "--- a/customers.py\n+++ b/customers.py\n@@ -31,3 +31,3 @@\n"
        changes = _parse_diff_changes(diff)
        assert len(changes) == 0

    def test_parses_enterprise_change(self):
        diff = "-ENTERPRISE_DISCOUNT: float = 0.10\n+ENTERPRISE_DISCOUNT: float = 0.15\n"
        changes = _parse_diff_changes(diff)
        syms = [c["symbol"] for c in changes]
        assert "ENTERPRISE_DISCOUNT" in syms

    def test_ignores_context_lines(self):
        diff = " SOME_CONSTANT: float = 0.05\n"  # context line, no + or -
        changes = _parse_diff_changes(diff)
        assert len(changes) == 0


class TestCorrelateChanges:
    def test_pairs_removed_and_added(self):
        raw = [
            {"symbol": "LOYALTY_DISCOUNT", "sign": "-", "value": "0.10", "raw_line": "-LOYALTY_DISCOUNT: float = 0.10"},
            {"symbol": "LOYALTY_DISCOUNT", "sign": "+", "value": "0.15", "raw_line": "+LOYALTY_DISCOUNT: float = 0.15"},
        ]
        result = _correlate_changes(raw)
        assert len(result) == 1
        ch = result[0]
        assert ch["symbol"] == "LOYALTY_DISCOUNT"
        assert ch["from_value"] == "0.10"
        assert ch["to_value"] == "0.15"

    def test_handles_addition_only(self):
        raw = [
            {"symbol": "NEW_CONST", "sign": "+", "value": "0.99", "raw_line": "+NEW_CONST = 0.99"},
        ]
        result = _correlate_changes(raw)
        assert result[0]["from_value"] is None
        assert result[0]["to_value"] == "0.99"


# ---------------------------------------------------------------------------
# DriftResult — failure scenario
# ---------------------------------------------------------------------------

class TestDriftDetectionFailure:
    def test_returns_drift_result(self, drift_failure):
        assert isinstance(drift_failure, DriftResult)

    def test_drift_is_detected(self, drift_failure):
        """The failure scenario must flag drift because Loyalty was changed."""
        assert drift_failure.drift_detected is True

    def test_status_is_drift_detected(self, drift_failure):
        assert drift_failure.status == "DRIFT_DETECTED"

    def test_loyalty_is_unintended(self, drift_failure):
        """LOYALTY_DISCOUNT must appear in unintended_changes."""
        unintended_syms = [u["symbol"] for u in drift_failure.unintended_changes]
        assert "LOYALTY_DISCOUNT" in unintended_syms

    def test_enterprise_is_intended(self, drift_failure):
        """ENTERPRISE_DISCOUNT must appear in intended_changes."""
        intended_syms = [i["symbol"] for i in drift_failure.intended_changes]
        assert "ENTERPRISE_DISCOUNT" in intended_syms

    def test_protected_violation_detected(self, drift_failure):
        """A violation of a protected clause must be recorded for LOYALTY."""
        assert len(drift_failure.protected_violations) >= 1
        violation_syms = [v["source_symbol"] for v in drift_failure.protected_violations]
        assert "LOYALTY_DISCOUNT" in violation_syms

    def test_protected_violation_has_correct_behavior_id(self, drift_failure):
        """The violation should reference behavior B002 (LOYALTY customer discount)."""
        b_ids = [v["behavior_id"] for v in drift_failure.protected_violations]
        assert "B002" in b_ids

    def test_protected_violation_has_severity(self, drift_failure):
        for v in drift_failure.protected_violations:
            assert v["severity"] in ("CRITICAL", "HIGH", "LOW")

    def test_summary_mentions_intent_drift(self, drift_failure):
        assert "INTENT DRIFT DETECTED" in drift_failure.summary

    def test_summary_mentions_blocked(self, drift_failure):
        assert "BLOCKED" in drift_failure.summary or "FAILED" in drift_failure.summary

    def test_summary_mentions_loyalty(self, drift_failure):
        assert "LOYALTY" in drift_failure.summary

    def test_to_dict_is_serialisable(self, drift_failure):
        d = drift_failure.to_dict()
        json.dumps(d)  # must not raise

    def test_to_dict_has_required_keys(self, drift_failure):
        d = drift_failure.to_dict()
        for key in [
            "drift_id", "detected_at", "contract_id", "allowed_symbol",
            "drift_detected", "intended_changes", "unintended_changes",
            "protected_violations", "status", "summary"
        ]:
            assert key in d, f"Missing key: {key}"

    def test_drift_id_is_uuid(self, drift_failure):
        import uuid
        uuid.UUID(drift_failure.to_dict()["drift_id"])  # must not raise


# ---------------------------------------------------------------------------
# DriftResult — success scenario
# ---------------------------------------------------------------------------

class TestDriftDetectionSuccess:
    def test_no_drift_detected(self, drift_success):
        """The success scenario has no drift — only Enterprise changed."""
        assert drift_success.drift_detected is False

    def test_status_is_clear(self, drift_success):
        assert drift_success.status == "CLEAR"

    def test_no_unintended_changes(self, drift_success):
        assert len(drift_success.unintended_changes) == 0

    def test_no_protected_violations(self, drift_success):
        assert len(drift_success.protected_violations) == 0

    def test_enterprise_is_intended(self, drift_success):
        intended_syms = [i["symbol"] for i in drift_success.intended_changes]
        assert "ENTERPRISE_DISCOUNT" in intended_syms

    def test_summary_says_clear(self, drift_success):
        assert "CLEAR" in drift_success.summary or "No intent drift" in drift_success.summary

    def test_intended_correct_flag_is_set(self, drift_success):
        assert drift_success.to_dict().get("intended_correct") is True


# ---------------------------------------------------------------------------
# Contract reference in DriftResult
# ---------------------------------------------------------------------------

class TestDriftContractReference:
    def test_contract_id_matches(self, pipeline, drift_failure):
        assert drift_failure.to_dict()["contract_id"] == pipeline["contract"].contract_id

    def test_allowed_symbol_is_enterprise(self, drift_failure):
        assert drift_failure.to_dict()["allowed_symbol"] == "ENTERPRISE_DISCOUNT"

    def test_allowed_file_is_customers(self, drift_failure):
        assert "customers" in drift_failure.to_dict()["allowed_file"]
