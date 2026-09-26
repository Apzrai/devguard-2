"""
test_bob_executor.py — Tests for devguard/bob_executor.py

Covers:
  - BobResponse structure
  - MockBobExecutor (failure and success scenarios)
  - get_executor() factory
  - WatsonxAgentExecutor raises NotImplementedError (stub contract)
  - WatsonxLLMExecutor raises EnvironmentError when unconfigured

All tests are deterministic and require no external API calls.
"""

import json
import pytest
from pathlib import Path

from devguard.understand import understand
from devguard.behavior_map import build_behavior_map
from devguard.evidence import collect_evidence
from devguard.contract import build_contract, make_enterprise_discount_request
from devguard.impact import analyze_impact
from devguard.bob_task import build_bob_task
from devguard.bob_executor import (
    BobExecutor,
    BobResponse,
    MockBobExecutor,
    WatsonxLLMExecutor,
    WatsonxAgentExecutor,
    get_executor,
)

SAMPLE_APP = Path(__file__).parent.parent.parent / "sample_app"


@pytest.fixture(scope="module")
def task():
    """Build a real BobTask from the actual pipeline."""
    u = understand(SAMPLE_APP)
    bmap = build_behavior_map(u)
    ev = collect_evidence(u)
    request = make_enterprise_discount_request()
    contract = build_contract(bmap, request)
    impact = analyze_impact(u, bmap, contract)
    return build_bob_task(u, bmap, ev, contract, impact, request)


# ---------------------------------------------------------------------------
# BobResponse
# ---------------------------------------------------------------------------

class TestBobResponse:
    def test_to_dict_has_all_required_keys(self):
        r = BobResponse(
            intent_summary="test",
            proposed_diff="--- a\n+++ b",
            files_modified=["customers.py"],
            raw="{}",
            executor_backend="mock",
            executed_at="2024-01-01T00:00:00+00:00",
        )
        d = r.to_dict()
        for key in ["intent_summary", "proposed_diff", "files_modified",
                    "raw", "executor_backend", "executed_at"]:
            assert key in d

    def test_to_json_is_valid(self):
        r = BobResponse(
            intent_summary="done",
            proposed_diff="-old\n+new",
            files_modified=["f.py"],
            raw="raw text",
            executor_backend="mock",
            executed_at="2024-01-01T00:00:00+00:00",
        )
        parsed = json.loads(r.to_json())
        assert parsed["executor_backend"] == "mock"


# ---------------------------------------------------------------------------
# MockBobExecutor — failure scenario (default)
# ---------------------------------------------------------------------------

class TestMockBobExecutorFailureScenario:
    def test_returns_bob_response(self, task):
        executor = MockBobExecutor(scenario="failure")
        response = executor.execute(task)
        assert isinstance(response, BobResponse)

    def test_backend_name_is_mock(self):
        assert MockBobExecutor().backend_name == "mock"

    def test_failure_diff_contains_loyalty_change(self, task):
        """The bad diff must change LOYALTY_DISCOUNT — that's the bug to detect."""
        response = MockBobExecutor(scenario="failure").execute(task)
        assert "LOYALTY_DISCOUNT" in response.proposed_diff
        assert "0.15" in response.proposed_diff

    def test_failure_diff_also_changes_enterprise(self, task):
        response = MockBobExecutor(scenario="failure").execute(task)
        assert "ENTERPRISE_DISCOUNT" in response.proposed_diff

    def test_failure_intent_does_not_admit_loyalty_change_directly(self, task):
        """Bob's intent in the failure scenario superficially looks aligned
        (it says it updated the enterprise rate) — drift detection must dig deeper."""
        response = MockBobExecutor(scenario="failure").execute(task)
        assert "enterprise" in response.intent_summary.lower()

    def test_failure_files_modified_includes_customers_py(self, task):
        response = MockBobExecutor(scenario="failure").execute(task)
        assert any("customers" in f for f in response.files_modified)

    def test_failure_executed_at_is_set(self, task):
        response = MockBobExecutor(scenario="failure").execute(task)
        assert "T" in response.executed_at


# ---------------------------------------------------------------------------
# MockBobExecutor — success scenario
# ---------------------------------------------------------------------------

class TestMockBobExecutorSuccessScenario:
    def test_success_diff_does_not_change_loyalty(self, task):
        """The good diff must NOT touch LOYALTY_DISCOUNT."""
        response = MockBobExecutor(scenario="success").execute(task)
        assert "LOYALTY_DISCOUNT" not in response.proposed_diff

    def test_success_diff_changes_enterprise(self, task):
        response = MockBobExecutor(scenario="success").execute(task)
        assert "ENTERPRISE_DISCOUNT" in response.proposed_diff
        assert "0.15" in response.proposed_diff

    def test_success_intent_says_only_enterprise_changed(self, task):
        response = MockBobExecutor(scenario="success").execute(task)
        assert "enterprise" in response.intent_summary.lower()

    def test_success_executor_backend_is_mock(self, task):
        response = MockBobExecutor(scenario="success").execute(task)
        assert response.executor_backend == "mock"

    def test_both_scenarios_return_files_modified(self, task):
        for scenario in ("failure", "success"):
            response = MockBobExecutor(scenario=scenario).execute(task)
            assert len(response.files_modified) >= 1

    def test_invalid_scenario_raises(self):
        with pytest.raises(ValueError, match="Unknown scenario"):
            MockBobExecutor(scenario="bad_value")


# ---------------------------------------------------------------------------
# Response serialisation
# ---------------------------------------------------------------------------

class TestResponseSerialisation:
    def test_mock_response_to_dict_is_serialisable(self, task):
        response = MockBobExecutor(scenario="failure").execute(task)
        d = response.to_dict()
        json.dumps(d)  # must not raise

    def test_mock_response_raw_is_valid_json(self, task):
        response = MockBobExecutor(scenario="failure").execute(task)
        parsed = json.loads(response.raw)
        assert "scenario" in parsed


# ---------------------------------------------------------------------------
# BobExecutor is an abstract base class
# ---------------------------------------------------------------------------

class TestBobExecutorIsAbstract:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BobExecutor()  # type: ignore

    def test_mock_is_subclass_of_bob_executor(self):
        assert issubclass(MockBobExecutor, BobExecutor)

    def test_watsonx_llm_is_subclass(self):
        assert issubclass(WatsonxLLMExecutor, BobExecutor)

    def test_watsonx_agent_is_subclass(self):
        assert issubclass(WatsonxAgentExecutor, BobExecutor)


# ---------------------------------------------------------------------------
# WatsonxAgentExecutor stub
# ---------------------------------------------------------------------------

class TestWatsonxAgentExecutorStub:
    def test_raises_not_implemented(self, task):
        executor = WatsonxAgentExecutor()
        with pytest.raises(NotImplementedError, match="not yet implemented"):
            executor.execute(task)

    def test_backend_name_is_watsonx_agent(self):
        assert WatsonxAgentExecutor().backend_name == "watsonx_agent"


# ---------------------------------------------------------------------------
# WatsonxLLMExecutor — unconfigured (no env vars set)
# ---------------------------------------------------------------------------

class TestWatsonxLLMExecutorUnconfigured:
    def test_is_not_configured_without_env_vars(self, monkeypatch):
        monkeypatch.delenv("WATSONX_API_KEY", raising=False)
        monkeypatch.delenv("WATSONX_PROJECT_ID", raising=False)
        executor = WatsonxLLMExecutor()
        assert not executor.is_configured()

    def test_execute_raises_environment_error_when_unconfigured(self, task, monkeypatch):
        monkeypatch.delenv("WATSONX_API_KEY", raising=False)
        monkeypatch.delenv("WATSONX_PROJECT_ID", raising=False)
        executor = WatsonxLLMExecutor()
        with pytest.raises(EnvironmentError, match="WATSONX_API_KEY"):
            executor.execute(task)

    def test_backend_name_is_watsonx_llm(self):
        assert WatsonxLLMExecutor().backend_name == "watsonx_llm"


# ---------------------------------------------------------------------------
# get_executor() factory
# ---------------------------------------------------------------------------

class TestGetExecutorFactory:
    def test_default_returns_mock_executor(self, monkeypatch):
        monkeypatch.delenv("BOB_BACKEND", raising=False)
        executor = get_executor()
        assert isinstance(executor, MockBobExecutor)

    def test_mock_backend_returns_mock_executor(self):
        executor = get_executor(backend="mock")
        assert isinstance(executor, MockBobExecutor)

    def test_watsonx_llm_backend_returns_llm_executor(self):
        executor = get_executor(backend="watsonx_llm")
        assert isinstance(executor, WatsonxLLMExecutor)

    def test_watsonx_agent_backend_returns_agent_executor(self):
        executor = get_executor(backend="watsonx_agent")
        assert isinstance(executor, WatsonxAgentExecutor)

    def test_env_var_is_respected(self, monkeypatch):
        monkeypatch.setenv("BOB_BACKEND", "mock")
        executor = get_executor()
        assert isinstance(executor, MockBobExecutor)

    def test_unknown_backend_raises(self):
        with pytest.raises(ValueError, match="Unknown BOB_BACKEND"):
            get_executor(backend="nonexistent_backend")

    def test_scenario_passed_to_mock(self):
        executor = get_executor(backend="mock", scenario="success")
        assert isinstance(executor, MockBobExecutor)
        assert executor.scenario == "success"

    def test_case_insensitive_backend_name(self):
        executor = get_executor(backend="MOCK")
        assert isinstance(executor, MockBobExecutor)
