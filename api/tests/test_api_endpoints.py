"""
api/tests/test_api_endpoints.py — Focused tests for the FastAPI layer.

Tests cover every route handler in api/main.py by calling the handler
functions directly (no HTTP server needed, no httpx/httpx2 dependency).
This mirrors how the existing DEVGUARD engine tests work: they call
engine functions directly rather than through a subprocess.

What is tested here:
  - Correct return types and required keys for every endpoint
  - CORS origins list is non-empty and contains the expected dev origins
  - OpenAPI schema is generated and contains all registered paths
  - Invalid project_root raises HTTP 400
  - Maintenance request defaults and custom fields round-trip correctly
  - Contract has protected clauses and success criteria
  - Impact analysis marks customers.py as directly affected
  - BobTask contains a bob_prompt and allowed_scope
  - Drift detection returns DRIFT_DETECTED for the mock failure scenario
  - Drift detection returns CLEAR for the mock success scenario
  - Verify returns FAILED / contract_not_satisfied for the failure scenario
  - Verify returns PASSED / contract_satisfied for the success scenario
  - Proof final_status matches the bob_scenario
  - None of the above modifies the canonical sample_app/ on disk

What is NOT tested here (already covered by devguard/tests/):
  - Internal engine correctness (behavior values, diff parsing, etc.)
  - Working-copy mechanics
  - Proof-of-done field details
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import all route handlers and request models from the API layer.
# No HTTP server, no httpx, no external dependency needed.
# ---------------------------------------------------------------------------
from api.main import (
    ALLOWED_ORIGINS,
    AnalyzeRequest,
    BobTaskRequest,
    ContractRequest,
    DriftRequest,
    ImpactRequest,
    MaintenanceRequestBody,
    VerifyRequest,
    analyze_impact_endpoint,
    analyze_repository,
    app,
    build_bob_task_endpoint,
    create_contract,
    create_maintenance,
    detect_drift_endpoint,
    get_proof_endpoint,
    health_check,
    verify_endpoint,
)
from fastapi import HTTPException

# Resolve the canonical sample_app so tests can confirm it is never modified.
_SAMPLE_APP = Path(__file__).resolve().parent.parent.parent / "sample_app"
_CUSTOMERS_PY = _SAMPLE_APP / "customers.py"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def customers_sha_before():
    """Record the SHA-256 of sample_app/customers.py before all tests."""
    import hashlib
    return hashlib.sha256(_CUSTOMERS_PY.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# GET /api/health
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    def test_returns_dict(self):
        result = health_check()
        assert isinstance(result, dict)

    def test_status_is_ok(self):
        assert health_check()["status"] == "ok"

    def test_service_name(self):
        assert health_check()["service"] == "DEVGUARD API"

    def test_version_is_present(self):
        assert "version" in health_check()


# ---------------------------------------------------------------------------
# CORS configuration
# ---------------------------------------------------------------------------

class TestCORSConfiguration:
    def test_allowed_origins_is_list(self):
        assert isinstance(ALLOWED_ORIGINS, list)

    def test_allowed_origins_is_non_empty(self):
        assert len(ALLOWED_ORIGINS) >= 1

    def test_localhost_3000_is_allowed(self):
        assert "http://localhost:3000" in ALLOWED_ORIGINS

    def test_localhost_5173_is_allowed(self):
        assert "http://localhost:5173" in ALLOWED_ORIGINS


# ---------------------------------------------------------------------------
# OpenAPI schema
# ---------------------------------------------------------------------------

class TestOpenAPISchema:
    def test_schema_is_dict(self):
        assert isinstance(app.openapi(), dict)

    def test_title_is_devguard_api(self):
        assert app.openapi()["info"]["title"] == "DEVGUARD API"

    def test_all_expected_paths_registered(self):
        paths = set(app.openapi()["paths"].keys())
        expected = {
            "/api/health",
            "/api/repository/analyze",
            "/api/maintenance",
            "/api/contract",
            "/api/impact",
            "/api/bob-task",
            "/api/drift",
            "/api/verify",
            "/api/proof",
        }
        assert expected.issubset(paths), f"Missing paths: {expected - paths}"

    def test_health_is_get(self):
        assert "get" in app.openapi()["paths"]["/api/health"]

    def test_proof_is_get(self):
        assert "get" in app.openapi()["paths"]["/api/proof"]

    def test_workflow_endpoints_are_post(self):
        schema = app.openapi()
        for path in [
            "/api/repository/analyze",
            "/api/maintenance",
            "/api/contract",
            "/api/impact",
            "/api/bob-task",
            "/api/drift",
            "/api/verify",
        ]:
            assert "post" in schema["paths"][path], f"{path} should be POST"


# ---------------------------------------------------------------------------
# POST /api/repository/analyze
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def analyze_result():
    return analyze_repository(AnalyzeRequest())


class TestAnalyzeEndpoint:
    def test_returns_dict(self, analyze_result):
        assert isinstance(analyze_result, dict)

    def test_has_source_files(self, analyze_result):
        assert "source_files" in analyze_result

    def test_has_test_files(self, analyze_result):
        assert "test_files" in analyze_result

    def test_has_constants(self, analyze_result):
        assert "constants" in analyze_result

    def test_has_provenance(self, analyze_result):
        assert analyze_result.get("provenance") == "OBSERVED"

    def test_seven_source_files_found(self, analyze_result):
        assert len(analyze_result["source_files"]) == 7

    def test_project_root_contains_sample_app(self, analyze_result):
        assert "sample_app" in analyze_result["project_root"]

    def test_invalid_project_root_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            analyze_repository(AnalyzeRequest(project_root="/nonexistent/path/xyz"))
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/maintenance
# ---------------------------------------------------------------------------

class TestMaintenanceEndpoint:
    def test_returns_dict(self):
        assert isinstance(create_maintenance(MaintenanceRequestBody()), dict)

    def test_default_target_symbol(self):
        result = create_maintenance(MaintenanceRequestBody())
        assert result["target_symbol"] == "ENTERPRISE_DISCOUNT"

    def test_default_target_file(self):
        result = create_maintenance(MaintenanceRequestBody())
        assert result["target_file"] == "customers.py"

    def test_default_current_value(self):
        result = create_maintenance(MaintenanceRequestBody())
        assert result["current_value"] == "0.10"

    def test_default_requested_value(self):
        result = create_maintenance(MaintenanceRequestBody())
        assert result["requested_value"] == "0.15"

    def test_default_target_behavior_id(self):
        result = create_maintenance(MaintenanceRequestBody())
        assert result["target_behavior_id"] == "B003"

    def test_custom_fields_round_trip(self):
        body = MaintenanceRequestBody(
            description="Custom desc",
            requestor="test-runner",
            notes="test notes",
        )
        result = create_maintenance(body)
        assert result["description"] == "Custom desc"
        assert result["requestor"] == "test-runner"
        assert result["notes"] == "test notes"

    def test_request_id_is_assigned_when_omitted(self):
        result = create_maintenance(MaintenanceRequestBody())
        assert result.get("request_id")

    def test_result_is_json_serialisable(self):
        result = create_maintenance(MaintenanceRequestBody())
        assert json.dumps(result)  # must not raise


# ---------------------------------------------------------------------------
# POST /api/contract
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def contract_result():
    return create_contract(ContractRequest())


class TestContractEndpoint:
    def test_returns_dict(self, contract_result):
        assert isinstance(contract_result, dict)

    def test_has_contract_id(self, contract_result):
        assert "contract_id" in contract_result

    def test_has_protected_behaviors(self, contract_result):
        assert "protected_behaviors" in contract_result
        assert len(contract_result["protected_behaviors"]) > 0

    def test_has_allowed_change(self, contract_result):
        assert "allowed_change" in contract_result

    def test_allowed_symbol_is_enterprise_discount(self, contract_result):
        assert contract_result["allowed_change"]["symbol"] == "ENTERPRISE_DISCOUNT"

    def test_has_success_criteria(self, contract_result):
        assert "success_criteria" in contract_result
        assert len(contract_result["success_criteria"]) > 0

    def test_maintenance_request_embedded(self, contract_result):
        assert "maintenance_request" in contract_result

    def test_result_is_json_serialisable(self, contract_result):
        assert json.dumps(contract_result)

    def test_invalid_project_root_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            create_contract(ContractRequest(project_root="/bad/path"))
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/impact
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def impact_result():
    return analyze_impact_endpoint(ImpactRequest())


class TestImpactEndpoint:
    def test_returns_dict(self, impact_result):
        assert isinstance(impact_result, dict)

    def test_has_impact_id(self, impact_result):
        assert "impact_id" in impact_result

    def test_has_directly_affected(self, impact_result):
        assert "directly_affected" in impact_result

    def test_customers_py_is_directly_affected(self, impact_result):
        files = [d["file"] for d in impact_result["directly_affected"]]
        assert any("customers" in f for f in files)

    def test_has_indirectly_affected(self, impact_result):
        assert "indirectly_affected" in impact_result

    def test_has_at_risk_tests(self, impact_result):
        assert "at_risk_tests" in impact_result
        assert len(impact_result["at_risk_tests"]) > 0

    def test_safe_to_change_is_true(self, impact_result):
        assert impact_result["safe_to_change"] is True

    def test_has_risk_summary(self, impact_result):
        assert "risk_summary" in impact_result
        assert len(impact_result["risk_summary"]) > 0

    def test_result_is_json_serialisable(self, impact_result):
        assert json.dumps(impact_result)


# ---------------------------------------------------------------------------
# POST /api/bob-task
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def bob_task_result():
    return build_bob_task_endpoint(BobTaskRequest())


class TestBobTaskEndpoint:
    def test_returns_dict(self, bob_task_result):
        assert isinstance(bob_task_result, dict)

    def test_has_task_id(self, bob_task_result):
        assert "task_id" in bob_task_result

    def test_has_bob_prompt(self, bob_task_result):
        assert "bob_prompt" in bob_task_result
        assert len(bob_task_result["bob_prompt"]) > 100

    def test_has_allowed_scope(self, bob_task_result):
        assert "allowed_scope" in bob_task_result

    def test_allowed_scope_symbol(self, bob_task_result):
        assert bob_task_result["allowed_scope"]["symbol"] == "ENTERPRISE_DISCOUNT"

    def test_has_protected_behaviors(self, bob_task_result):
        assert len(bob_task_result["protected_behaviors"]) > 0

    def test_has_success_criteria(self, bob_task_result):
        assert len(bob_task_result["success_criteria"]) > 0

    def test_has_evidence_summary(self, bob_task_result):
        assert "evidence_summary" in bob_task_result
        assert "aggregate_hash" in bob_task_result["evidence_summary"]

    def test_has_file_context(self, bob_task_result):
        assert "file_context" in bob_task_result
        assert "content" in bob_task_result["file_context"]

    def test_result_is_json_serialisable(self, bob_task_result):
        assert json.dumps(bob_task_result)


# ---------------------------------------------------------------------------
# POST /api/drift
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def drift_failure_result():
    return detect_drift_endpoint(DriftRequest(bob_scenario="failure"))


@pytest.fixture(scope="module")
def drift_success_result():
    return detect_drift_endpoint(DriftRequest(bob_scenario="success"))


class TestDriftEndpointFailureScenario:
    def test_returns_dict(self, drift_failure_result):
        assert isinstance(drift_failure_result, dict)

    def test_has_drift_id(self, drift_failure_result):
        assert "drift_id" in drift_failure_result

    def test_drift_detected_is_true(self, drift_failure_result):
        assert drift_failure_result["drift_detected"] is True

    def test_status_is_drift_detected(self, drift_failure_result):
        assert drift_failure_result["status"] == "DRIFT_DETECTED"

    def test_has_unintended_changes(self, drift_failure_result):
        assert len(drift_failure_result["unintended_changes"]) > 0

    def test_loyalty_is_in_unintended_changes(self, drift_failure_result):
        symbols = [u["symbol"] for u in drift_failure_result["unintended_changes"]]
        assert "LOYALTY_DISCOUNT" in symbols

    def test_has_protected_violations(self, drift_failure_result):
        assert len(drift_failure_result["protected_violations"]) > 0

    def test_summary_mentions_drift(self, drift_failure_result):
        assert "DRIFT" in drift_failure_result["summary"].upper()

    def test_result_is_json_serialisable(self, drift_failure_result):
        assert json.dumps(drift_failure_result)


class TestDriftEndpointSuccessScenario:
    def test_drift_detected_is_false(self, drift_success_result):
        assert drift_success_result["drift_detected"] is False

    def test_status_is_clear(self, drift_success_result):
        assert drift_success_result["status"] == "CLEAR"

    def test_no_unintended_changes(self, drift_success_result):
        assert drift_success_result["unintended_changes"] == []

    def test_no_protected_violations(self, drift_success_result):
        assert drift_success_result["protected_violations"] == []

    def test_enterprise_is_intended(self, drift_success_result):
        symbols = [c["symbol"] for c in drift_success_result["intended_changes"]]
        assert "ENTERPRISE_DISCOUNT" in symbols


# ---------------------------------------------------------------------------
# POST /api/verify  (runs pytest internally — slow but correct)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def verify_failure_result():
    return verify_endpoint(VerifyRequest(bob_scenario="failure"))


@pytest.fixture(scope="module")
def verify_success_result():
    return verify_endpoint(VerifyRequest(bob_scenario="success"))


class TestVerifyEndpointFailureScenario:
    def test_returns_dict(self, verify_failure_result):
        assert isinstance(verify_failure_result, dict)

    def test_has_verification_id(self, verify_failure_result):
        assert "verification_id" in verify_failure_result

    def test_status_is_failed(self, verify_failure_result):
        assert verify_failure_result["status"] == "FAILED"

    def test_contract_not_satisfied(self, verify_failure_result):
        assert verify_failure_result["contract_satisfied"] is False

    def test_protected_behavior_violated(self, verify_failure_result):
        assert verify_failure_result["protected_behavior_preserved"] is False

    def test_has_protected_tests_failed(self, verify_failure_result):
        assert len(verify_failure_result["protected_tests_failed"]) > 0

    def test_unexpected_changes_includes_loyalty(self, verify_failure_result):
        assert "LOYALTY_DISCOUNT" in verify_failure_result["unexpected_changes"]

    def test_result_is_json_serialisable(self, verify_failure_result):
        assert json.dumps(verify_failure_result)


class TestVerifyEndpointSuccessScenario:
    def test_status_is_passed(self, verify_success_result):
        assert verify_success_result["status"] == "PASSED"

    def test_contract_satisfied(self, verify_success_result):
        assert verify_success_result["contract_satisfied"] is True

    def test_protected_behavior_preserved(self, verify_success_result):
        assert verify_success_result["protected_behavior_preserved"] is True

    def test_no_protected_test_failures(self, verify_success_result):
        assert verify_success_result["protected_tests_failed"] == []

    def test_no_unexpected_changes(self, verify_success_result):
        assert verify_success_result["unexpected_changes"] == []


# ---------------------------------------------------------------------------
# GET /api/proof  (runs pytest internally — slow but correct)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def proof_failure_result():
    return get_proof_endpoint(bob_scenario="failure")


@pytest.fixture(scope="module")
def proof_success_result():
    return get_proof_endpoint(bob_scenario="success")


class TestProofEndpointFailureScenario:
    def test_returns_dict(self, proof_failure_result):
        assert isinstance(proof_failure_result, dict)

    def test_has_proof_id(self, proof_failure_result):
        assert "proof_id" in proof_failure_result

    def test_final_status_is_blocked(self, proof_failure_result):
        assert proof_failure_result["final_status"] == "BLOCKED / FAILED"

    def test_contract_not_satisfied(self, proof_failure_result):
        assert proof_failure_result["contract_satisfied"] is False

    def test_drift_detected(self, proof_failure_result):
        assert proof_failure_result["intent_drift"]["drift_detected"] is True

    def test_result_is_json_serialisable(self, proof_failure_result):
        assert json.dumps(proof_failure_result)


class TestProofEndpointSuccessScenario:
    def test_final_status_is_verified(self, proof_success_result):
        assert proof_success_result["final_status"] == "VERIFIED"

    def test_contract_satisfied(self, proof_success_result):
        assert proof_success_result["contract_satisfied"] is True

    def test_drift_not_detected(self, proof_success_result):
        assert proof_success_result["intent_drift"]["drift_detected"] is False


# ---------------------------------------------------------------------------
# Canonical sample_app is never modified by any API call
# ---------------------------------------------------------------------------

class TestCanonicalProjectUnmodified:
    def test_customers_py_sha_unchanged_after_all_api_calls(
        self, customers_sha_before, verify_failure_result, verify_success_result,
        proof_failure_result, proof_success_result,
    ):
        """The API must never touch the canonical sample_app/ on disk."""
        import hashlib
        sha_after = hashlib.sha256(_CUSTOMERS_PY.read_bytes()).hexdigest()
        assert sha_after == customers_sha_before, (
            "sample_app/customers.py was modified by an API call — "
            "working-copy isolation is broken."
        )
