"""
test_bob_task.py — Tests for devguard/bob_task.py

Verifies that build_bob_task() correctly assembles all DEVGUARD pipeline
artifacts into a complete, self-contained BobTask.

All tests run against the actual sample_app/ pipeline — no mocking.
"""

import json
import pytest
from pathlib import Path

from devguard.understand import understand
from devguard.behavior_map import build_behavior_map
from devguard.evidence import collect_evidence
from devguard.contract import build_contract, make_enterprise_discount_request
from devguard.impact import analyze_impact
from devguard.bob_task import build_bob_task, BobTask

SAMPLE_APP = Path(__file__).parent.parent.parent / "sample_app"


@pytest.fixture(scope="module")
def pipeline():
    """Run the full DEVGUARD pipeline once and share results."""
    u = understand(SAMPLE_APP)
    bmap = build_behavior_map(u)
    ev = collect_evidence(u)
    request = make_enterprise_discount_request()
    contract = build_contract(bmap, request)
    impact = analyze_impact(u, bmap, contract)
    task = build_bob_task(u, bmap, ev, contract, impact, request)
    return {
        "u": u, "bmap": bmap, "ev": ev,
        "contract": contract, "impact": impact,
        "request": request, "task": task,
    }


@pytest.fixture(scope="module")
def task(pipeline):
    return pipeline["task"]


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

class TestBobTaskStructure:
    def test_returns_bob_task_instance(self, task):
        assert isinstance(task, BobTask)

    def test_has_task_id(self, task):
        assert len(task.task_id) == 36  # UUID

    def test_has_created_at(self, task):
        assert "T" in task.created_at

    def test_has_title(self, task):
        assert "Enterprise" in task.title or "enterprise" in task.title.lower()

    def test_to_dict_is_complete(self, task):
        d = task.to_dict()
        for key in [
            "task_id", "created_at", "title",
            "maintenance_request", "current_behavior", "evidence_summary",
            "contract", "impact", "file_context",
            "allowed_scope", "protected_behaviors", "success_criteria", "bob_prompt",
        ]:
            assert key in d, f"Missing key: {key}"

    def test_to_json_is_valid_json(self, task):
        raw = task.to_json()
        parsed = json.loads(raw)
        assert "task_id" in parsed


# ---------------------------------------------------------------------------
# Maintenance request payload
# ---------------------------------------------------------------------------

class TestMaintenanceRequestPayload:
    def test_request_description_mentions_enterprise(self, task):
        assert "Enterprise" in task.maintenance_request["description"]

    def test_request_target_symbol_is_enterprise_discount(self, task):
        assert task.maintenance_request["target_symbol"] == "ENTERPRISE_DISCOUNT"

    def test_request_target_file_is_customers_py(self, task):
        assert task.maintenance_request["target_file"] == "customers.py"

    def test_request_current_value_is_0_10(self, task):
        assert task.maintenance_request["current_value"] == "0.10"

    def test_request_new_value_is_0_15(self, task):
        assert task.maintenance_request["requested_value"] == "0.15"


# ---------------------------------------------------------------------------
# Evidence summary
# ---------------------------------------------------------------------------

class TestEvidenceSummary:
    def test_evidence_summary_has_aggregate_hash(self, task):
        assert len(task.evidence_summary["aggregate_hash"]) == 64

    def test_evidence_summary_has_total_files(self, task):
        assert task.evidence_summary["total_files"] > 0

    def test_evidence_summary_has_total_test_functions(self, task):
        assert task.evidence_summary["total_test_functions"] >= 100

    def test_evidence_summary_has_recorded_at(self, task):
        assert "T" in task.evidence_summary["recorded_at"]


# ---------------------------------------------------------------------------
# File context
# ---------------------------------------------------------------------------

class TestFileContext:
    def test_file_context_has_relative_path(self, task):
        assert "customers.py" in task.file_context["relative_path"]

    def test_file_context_has_sha256(self, task):
        sha = task.file_context["sha256"]
        assert len(sha) == 64
        assert sha.isalnum()

    def test_file_context_contains_actual_source_content(self, task):
        content = task.file_context["content"]
        # Verify actual constants are present in the snapshot
        assert "ENTERPRISE_DISCOUNT" in content
        assert "LOYALTY_DISCOUNT" in content
        assert "NEW_CUSTOMER_DISCOUNT" in content

    def test_file_context_shows_current_enterprise_value(self, task):
        """The file context must capture the CURRENT value, not the new one."""
        content = task.file_context["content"]
        assert "0.10" in content  # current enterprise rate

    def test_file_context_sha256_matches_evidence(self, task, pipeline):
        """SHA-256 in file_context must match what evidence recorded."""
        ev = pipeline["ev"]
        ev_hash = ev.get_hash("customers.py")
        assert task.file_context["sha256"] == ev_hash


# ---------------------------------------------------------------------------
# Allowed scope
# ---------------------------------------------------------------------------

class TestAllowedScope:
    def test_allowed_scope_symbol_is_enterprise_discount(self, task):
        assert task.allowed_scope["symbol"] == "ENTERPRISE_DISCOUNT"

    def test_allowed_scope_file_is_customers_py(self, task):
        assert task.allowed_scope["file"] == "customers.py"

    def test_allowed_scope_from_value(self, task):
        assert task.allowed_scope["from_value"] == "0.10"

    def test_allowed_scope_to_value(self, task):
        assert task.allowed_scope["to_value"] == "0.15"

    def test_allowed_scope_note_mentions_only_one_symbol(self, task):
        note = task.allowed_scope["scope_note"]
        assert "ENTERPRISE_DISCOUNT" in note
        assert "only" in note.lower() or "Only" in note


# ---------------------------------------------------------------------------
# Protected behaviors
# ---------------------------------------------------------------------------

class TestProtectedBehaviors:
    def test_protected_behaviors_is_non_empty(self, task):
        assert len(task.protected_behaviors) >= 5

    def test_b003_not_in_protected_behaviors(self, task):
        ids = [c["behavior_id"] for c in task.protected_behaviors]
        assert "B003" not in ids

    def test_b002_loyalty_is_protected(self, task):
        ids = {c["behavior_id"] for c in task.protected_behaviors}
        assert "B002" in ids

    def test_b008_independence_is_protected(self, task):
        ids = {c["behavior_id"] for c in task.protected_behaviors}
        assert "B008" in ids

    def test_loyalty_must_not_is_present(self, task):
        loyalty_clause = next(
            c for c in task.protected_behaviors if c["behavior_id"] == "B002"
        )
        assert "LOYALTY_DISCOUNT" in loyalty_clause["must_not"]


# ---------------------------------------------------------------------------
# Success criteria
# ---------------------------------------------------------------------------

class TestSuccessCriteria:
    def test_success_criteria_is_non_empty(self, task):
        assert len(task.success_criteria) >= 5

    def test_success_criteria_mentions_enterprise(self, task):
        text = " ".join(task.success_criteria)
        assert "ENTERPRISE_DISCOUNT" in text

    def test_success_criteria_mentions_loyalty(self, task):
        text = " ".join(task.success_criteria)
        assert "LOYALTY" in text

    def test_success_criteria_mentions_tests(self, task):
        text = " ".join(task.success_criteria)
        assert "test" in text.lower()


# ---------------------------------------------------------------------------
# Bob prompt
# ---------------------------------------------------------------------------

class TestBobPrompt:
    def test_bob_prompt_is_non_empty(self, task):
        assert len(task.bob_prompt) > 100

    def test_bob_prompt_contains_task_description(self, task):
        assert "Enterprise" in task.bob_prompt

    def test_bob_prompt_contains_target_symbol(self, task):
        assert "ENTERPRISE_DISCOUNT" in task.bob_prompt

    def test_bob_prompt_contains_from_to_values(self, task):
        assert "0.10" in task.bob_prompt
        assert "0.15" in task.bob_prompt

    def test_bob_prompt_contains_target_file(self, task):
        assert "customers.py" in task.bob_prompt

    def test_bob_prompt_contains_protected_behavior_warning(self, task):
        # Prompt must warn about LOYALTY_DISCOUNT
        assert "LOYALTY" in task.bob_prompt

    def test_bob_prompt_contains_success_criteria(self, task):
        assert "SUCCESS CRITERIA" in task.bob_prompt.upper() or "success" in task.bob_prompt.lower()

    def test_bob_prompt_contains_actual_file_content(self, task):
        # The full file content is embedded in the prompt
        assert "ENTERPRISE_DISCOUNT" in task.bob_prompt
        assert "LOYALTY_DISCOUNT" in task.bob_prompt

    def test_bob_prompt_instructions_mention_single_line_change(self, task):
        assert "only" in task.bob_prompt.lower() or "Only" in task.bob_prompt

    def test_bob_prompt_is_self_contained(self, task):
        """The prompt must contain everything Bob needs without additional context."""
        for required in [
            "ENTERPRISE_DISCOUNT",   # target symbol
            "customers.py",          # target file
            "LOYALTY",               # protected behavior warning
            "pytest",                # test run instruction
        ]:
            assert required in task.bob_prompt, f"Prompt missing: {required}"


# ---------------------------------------------------------------------------
# Impact summary in task
# ---------------------------------------------------------------------------

class TestImpactSummary:
    def test_impact_summary_has_directly_affected(self, task):
        assert len(task.impact["directly_affected"]) >= 1

    def test_impact_summary_directly_affected_includes_customers_py(self, task):
        files = task.impact["directly_affected"]
        assert any("customers" in f for f in files)

    def test_impact_summary_safe_to_change_is_true(self, task):
        assert task.impact["safe_to_change"] is True

    def test_impact_summary_high_risk_test_count_is_positive(self, task):
        assert task.impact["high_risk_test_count"] > 0


# ---------------------------------------------------------------------------
# Serialisation and persistence
# ---------------------------------------------------------------------------

class TestBobTaskSerialisation:
    def test_to_dict_is_json_serialisable(self, task):
        d = task.to_dict()
        # Must not raise
        json.dumps(d)

    def test_save_writes_file(self, task, tmp_path):
        out = tmp_path / "bob_task.json"
        saved = task.save(out)
        assert saved.exists()
        content = json.loads(saved.read_text())
        assert content["task_id"] == task.task_id
