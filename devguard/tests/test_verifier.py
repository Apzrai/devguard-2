"""
test_verifier.py — Tests for devguard/verifier.py

Covers:
  - Working copy creation and cleanup
  - Patch application to working copy
  - Controlled failure: bad diff fails tests, protected behaviors detected
  - Corrected change: passes tests, contract satisfied
  - VerificationResult structure and serialisation
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
from devguard.drift_detector import detect_drift
from devguard.verifier import (
    VerificationResult,
    verify,
    _create_working_copy,
    _apply_patch_to_working_copy,
    _read_symbol_value,
    cleanup_working_copy,
)

SAMPLE_APP = Path(__file__).parent.parent.parent / "sample_app"


# ---------------------------------------------------------------------------
# Shared fixtures
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
    return {"u": u, "bmap": bmap, "ev": ev, "request": request,
            "contract": contract, "impact": impact, "task": task}


@pytest.fixture(scope="module")
def bad_response(pipeline):
    return MockBobExecutor(scenario="failure").execute(pipeline["task"])


@pytest.fixture(scope="module")
def good_response(pipeline):
    return MockBobExecutor(scenario="success").execute(pipeline["task"])


@pytest.fixture(scope="module")
def drift_failure(pipeline, bad_response):
    return detect_drift(pipeline["contract"], bad_response)


@pytest.fixture(scope="module")
def drift_success(pipeline, good_response):
    return detect_drift(pipeline["contract"], good_response)


@pytest.fixture(scope="module")
def verification_failure(pipeline, bad_response, drift_failure):
    """Run verification on the controlled-failure scenario."""
    return verify(pipeline["contract"], bad_response, drift_failure, SAMPLE_APP)


@pytest.fixture(scope="module")
def verification_success(pipeline, good_response, drift_success):
    """Run verification on the corrected scenario."""
    return verify(pipeline["contract"], good_response, drift_success, SAMPLE_APP)


# ---------------------------------------------------------------------------
# Working copy management
# ---------------------------------------------------------------------------

class TestWorkingCopy:
    def test_creates_copy_of_source(self):
        wc = _create_working_copy(SAMPLE_APP)
        try:
            assert wc.exists()
            assert wc.name == "sample_app"
            # The canonical sample_app must not be the same directory
            assert wc != SAMPLE_APP
        finally:
            cleanup_working_copy(wc)

    def test_canonical_unchanged_after_copy(self):
        original_content = (SAMPLE_APP / "customers.py").read_text(encoding="utf-8")
        wc = _create_working_copy(SAMPLE_APP)
        try:
            wc_content = (wc / "customers.py").read_text(encoding="utf-8")
            assert wc_content == original_content
        finally:
            cleanup_working_copy(wc)

    def test_cleanup_removes_directory(self):
        wc = _create_working_copy(SAMPLE_APP)
        parent = wc.parent
        cleanup_working_copy(wc)
        assert not parent.exists()


# ---------------------------------------------------------------------------
# Patch application
# ---------------------------------------------------------------------------

class TestPatchApplication:
    def test_apply_patch_changes_symbol_value(self):
        wc = _create_working_copy(SAMPLE_APP)
        try:
            ok = _apply_patch_to_working_copy(wc, "customers.py", "LOYALTY_DISCOUNT", "0.20")
            assert ok is True
            val = _read_symbol_value(wc, "customers.py", "LOYALTY_DISCOUNT")
            assert val is not None
            assert "0.20" in val
        finally:
            cleanup_working_copy(wc)

    def test_canonical_not_modified(self):
        wc = _create_working_copy(SAMPLE_APP)
        try:
            _apply_patch_to_working_copy(wc, "customers.py", "LOYALTY_DISCOUNT", "0.99")
        finally:
            cleanup_working_copy(wc)
        # Canonical must still have original value
        from sample_app.customers import LOYALTY_DISCOUNT
        assert LOYALTY_DISCOUNT == pytest.approx(0.10)

    def test_apply_returns_false_for_missing_symbol(self):
        wc = _create_working_copy(SAMPLE_APP)
        try:
            ok = _apply_patch_to_working_copy(wc, "customers.py", "NONEXISTENT_SYMBOL", "0.99")
            assert ok is False
        finally:
            cleanup_working_copy(wc)

    def test_apply_returns_false_for_missing_file(self):
        wc = _create_working_copy(SAMPLE_APP)
        try:
            ok = _apply_patch_to_working_copy(wc, "nonexistent.py", "SOME_SYMBOL", "0.99")
            assert ok is False
        finally:
            cleanup_working_copy(wc)


# ---------------------------------------------------------------------------
# Read symbol value
# ---------------------------------------------------------------------------

class TestReadSymbolValue:
    def test_reads_loyalty_discount(self):
        wc = _create_working_copy(SAMPLE_APP)
        try:
            val = _read_symbol_value(wc, "customers.py", "LOYALTY_DISCOUNT")
            assert val is not None
            assert "0.10" in val
        finally:
            cleanup_working_copy(wc)

    def test_reads_enterprise_discount(self):
        wc = _create_working_copy(SAMPLE_APP)
        try:
            val = _read_symbol_value(wc, "customers.py", "ENTERPRISE_DISCOUNT")
            assert val is not None
            assert "0.10" in val
        finally:
            cleanup_working_copy(wc)

    def test_returns_none_for_missing_symbol(self):
        wc = _create_working_copy(SAMPLE_APP)
        try:
            val = _read_symbol_value(wc, "customers.py", "DOES_NOT_EXIST")
            assert val is None
        finally:
            cleanup_working_copy(wc)


# ---------------------------------------------------------------------------
# Controlled failure verification
# ---------------------------------------------------------------------------

class TestControlledFailureVerification:
    def test_returns_verification_result(self, verification_failure):
        assert isinstance(verification_failure, VerificationResult)

    def test_status_is_failed(self, verification_failure):
        """The bad diff must produce a FAILED verification."""
        assert verification_failure.status == "FAILED"

    def test_contract_not_satisfied(self, verification_failure):
        assert verification_failure.contract_satisfied is False

    def test_protected_behavior_violated(self, verification_failure):
        """Loyalty tests must fail because LOYALTY_DISCOUNT was changed."""
        assert verification_failure.protected_behavior_preserved is False

    def test_protected_tests_failed_contains_loyalty_tests(self, verification_failure):
        """At least one loyalty-related test must be in the protected failures."""
        protected_failures = verification_failure.protected_tests_failed
        assert len(protected_failures) >= 1
        # At least one failure should be loyalty-related
        loyalty_related = any(
            "loyalty" in t.lower() or "independence" in t.lower()
            for t in protected_failures
        )
        assert loyalty_related, f"Expected loyalty-related failure in: {protected_failures}"

    def test_has_actual_failed_tests(self, verification_failure):
        """Failures must be real pytest failures, not fabricated.

        The raw test suite will fail because both Enterprise and Loyalty were
        changed; protected_tests_failed captures the genuine violations.
        """
        assert len(verification_failure.protected_tests_failed) > 0
        assert len(verification_failure.failed_test_ids) > 0

    def test_requested_behavior_is_correct(self, verification_failure):
        """Enterprise discount IS updated to 0.15 — that part was correct."""
        assert verification_failure.requested_behavior_correct is True

    def test_unexpected_changes_includes_loyalty(self, verification_failure):
        """LOYALTY_DISCOUNT must be flagged as an unexpected change."""
        assert "LOYALTY_DISCOUNT" in verification_failure.to_dict()["unexpected_changes"]

    def test_summary_mentions_protected_violation(self, verification_failure):
        summary = verification_failure.summary.upper()
        assert "PROTECTED" in summary or "VIOLATED" in summary or "FAILED" in summary

    def test_to_dict_is_serialisable(self, verification_failure):
        d = verification_failure.to_dict()
        json.dumps(d)  # must not raise

    def test_to_dict_has_required_keys(self, verification_failure):
        d = verification_failure.to_dict()
        for key in [
            "verification_id", "verified_at", "contract_id",
            "tests_run", "tests_passed", "tests_failed",
            "failed_test_ids", "protected_tests_failed",
            "requested_behavior_correct", "protected_behavior_preserved",
            "unexpected_changes", "contract_satisfied", "status", "summary"
        ]:
            assert key in d, f"Missing key: {key}"

    def test_tests_run_is_positive(self, verification_failure):
        assert verification_failure.to_dict()["tests_run"] > 0


# ---------------------------------------------------------------------------
# Corrected (successful) verification
# ---------------------------------------------------------------------------

class TestCorrectedVerification:
    def test_status_is_passed(self, verification_success):
        """The corrected diff must produce a PASSED verification."""
        assert verification_success.status == "PASSED"

    def test_contract_satisfied(self, verification_success):
        assert verification_success.contract_satisfied is True

    def test_requested_behavior_correct(self, verification_success):
        assert verification_success.requested_behavior_correct is True

    def test_protected_behavior_preserved(self, verification_success):
        assert verification_success.protected_behavior_preserved is True

    def test_no_protected_test_failures(self, verification_success):
        assert len(verification_success.protected_tests_failed) == 0

    def test_no_test_failures(self, verification_success):
        """No protected-behavior failures after the correct Enterprise-only change."""
        assert len(verification_success.protected_tests_failed) == 0

    def test_no_unexpected_changes(self, verification_success):
        assert verification_success.to_dict()["unexpected_changes"] == []

    def test_summary_says_passed(self, verification_success):
        assert "PASSED" in verification_success.summary or "passed" in verification_success.summary

    def test_summary_confirms_enterprise_changed(self, verification_success):
        assert "ENTERPRISE_DISCOUNT" in verification_success.summary or "0.15" in verification_success.summary

    def test_canonical_sample_app_unchanged(self):
        """Verify the canonical sample_app was never modified by any test."""
        from sample_app.customers import ENTERPRISE_DISCOUNT, LOYALTY_DISCOUNT
        assert ENTERPRISE_DISCOUNT == pytest.approx(0.10)
        assert LOYALTY_DISCOUNT == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# End-to-end: full Phase 5 workflow
# ---------------------------------------------------------------------------

class TestPhase5EndToEnd:
    """Full workflow: request → contract → Bob executes → drift detected →
    verification FAILED → corrected change → verification PASSED."""

    def test_failure_then_correction_workflow(self, pipeline):
        """Full Phase 5 workflow in one test."""
        contract = pipeline["contract"]
        task = pipeline["task"]

        # Step 1: Bob proposes the bad change
        bad_resp = MockBobExecutor(scenario="failure").execute(task)

        # Step 2: Detect drift
        drift = detect_drift(contract, bad_resp)
        assert drift.drift_detected is True
        assert drift.status == "DRIFT_DETECTED"

        # Step 3: Verify — must fail
        vr_fail = verify(contract, bad_resp, drift, SAMPLE_APP)
        assert vr_fail.status == "FAILED"
        assert not vr_fail.contract_satisfied
        assert not vr_fail.protected_behavior_preserved

        # Step 4: Bob proposes the corrected change
        good_resp = MockBobExecutor(scenario="success").execute(task)

        # Step 5: Detect drift — must be clear
        drift_ok = detect_drift(contract, good_resp)
        assert drift_ok.drift_detected is False
        assert drift_ok.status == "CLEAR"

        # Step 6: Verify — must pass
        vr_pass = verify(contract, good_resp, drift_ok, SAMPLE_APP)
        assert vr_pass.status == "PASSED"
        assert vr_pass.contract_satisfied
        assert vr_pass.requested_behavior_correct
        assert vr_pass.protected_behavior_preserved
        assert len(vr_pass.protected_tests_failed) == 0

    def test_canonical_sample_app_never_modified(self):
        """The canonical sample_app must be pristine throughout all Phase 5 tests."""
        from sample_app.customers import (
            ENTERPRISE_DISCOUNT, LOYALTY_DISCOUNT, NEW_CUSTOMER_DISCOUNT
        )
        assert ENTERPRISE_DISCOUNT == pytest.approx(0.10)
        assert LOYALTY_DISCOUNT == pytest.approx(0.10)
        assert NEW_CUSTOMER_DISCOUNT == pytest.approx(0.05)
