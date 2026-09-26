"""
test_contract.py — Tests for devguard/contract.py
"""

import pytest
from pathlib import Path

from devguard.understand import understand
from devguard.behavior_map import build_behavior_map
from devguard.contract import (
    build_contract,
    make_enterprise_discount_request,
    BehavioralContract,
    MaintenanceRequest,
)

SAMPLE_APP = Path(__file__).parent.parent.parent / "sample_app"


@pytest.fixture(scope="module")
def contract():
    u = understand(SAMPLE_APP)
    bmap = build_behavior_map(u)
    request = make_enterprise_discount_request()
    return build_contract(bmap, request)


@pytest.fixture(scope="module")
def request_obj():
    return make_enterprise_discount_request()


class TestMaintenanceRequest:
    def test_request_has_correct_description(self, request_obj):
        assert "Enterprise" in request_obj.description
        assert "10%" in request_obj.description or "15%" in request_obj.description

    def test_request_targets_b003(self, request_obj):
        assert request_obj.target_behavior_id == "B003"

    def test_request_targets_enterprise_discount_symbol(self, request_obj):
        assert request_obj.target_symbol == "ENTERPRISE_DISCOUNT"

    def test_request_targets_customers_file(self, request_obj):
        assert request_obj.target_file == "customers.py"

    def test_request_current_value_is_0_10(self, request_obj):
        assert request_obj.current_value == "0.10"

    def test_request_new_value_is_0_15(self, request_obj):
        assert request_obj.requested_value == "0.15"

    def test_request_to_dict_is_serialisable(self, request_obj):
        d = request_obj.to_dict()
        assert isinstance(d, dict)
        assert "description" in d


class TestContractStructure:
    def test_returns_behavioral_contract_instance(self, contract):
        assert isinstance(contract, BehavioralContract)

    def test_contract_has_id(self, contract):
        assert len(contract.contract_id) == 36

    def test_contract_has_maintenance_request(self, contract):
        assert "maintenance_request" in contract.to_dict()

    def test_contract_has_allowed_change(self, contract):
        ac = contract.allowed_change
        assert ac["symbol"] == "ENTERPRISE_DISCOUNT"
        assert ac["file"] == "customers.py"

    def test_allowed_change_from_value_is_0_10(self, contract):
        assert contract.allowed_change["from_value"] == "0.10"

    def test_allowed_change_to_value_is_0_15(self, contract):
        assert contract.allowed_change["to_value"] == "0.15"

    def test_allowed_change_scope_note_mentions_only_one_symbol(self, contract):
        note = contract.allowed_change["scope_note"]
        assert "ENTERPRISE_DISCOUNT" in note
        assert "Only" in note or "only" in note

    def test_has_protected_behaviors(self, contract):
        assert len(contract.protected_clauses) >= 5

    def test_has_success_criteria(self, contract):
        assert len(contract.success_criteria) >= 5


class TestProtectedClauses:
    def test_b003_is_not_in_protected_clauses(self, contract):
        """B003 (ENTERPRISE_DISCOUNT) is the target — it must NOT appear as protected."""
        clause_ids = [c["behavior_id"] for c in contract.protected_clauses]
        assert "B003" not in clause_ids

    def test_b001_is_protected(self, contract):
        clause = contract.get_clause("B001")
        assert clause is not None
        assert "NEW" in clause["invariant"] or "NEW_CUSTOMER_DISCOUNT" in clause["must_not"]

    def test_b002_is_protected(self, contract):
        clause = contract.get_clause("B002")
        assert clause is not None
        assert "LOYALTY" in clause["invariant"] or "LOYALTY_DISCOUNT" in clause["must_not"]

    def test_b002_must_not_mentions_loyalty(self, contract):
        clause = contract.get_clause("B002")
        assert "LOYALTY_DISCOUNT" in clause["must_not"]

    def test_b008_independence_clause_exists(self, contract):
        clause = contract.get_clause("B008")
        assert clause is not None
        assert "independent" in clause["invariant"].lower()

    def test_b008_must_not_prohibits_loyalty_change(self, contract):
        clause = contract.get_clause("B008")
        assert "LOYALTY_DISCOUNT" in clause["must_not"]
        assert "ENTERPRISE_DISCOUNT" in clause["must_not"]

    def test_b004_ordering_is_critical(self, contract):
        clause = contract.get_clause("B004")
        assert clause is not None
        assert clause["severity"] == "CRITICAL"

    def test_all_clauses_have_test_anchors(self, contract):
        for clause in contract.protected_clauses:
            assert len(clause["test_anchors"]) > 0, \
                f"Clause {clause['behavior_id']} has no test anchors"

    def test_all_clauses_have_severity(self, contract):
        valid = {"CRITICAL", "HIGH", "LOW"}
        for clause in contract.protected_clauses:
            assert clause["severity"] in valid


class TestSuccessCriteria:
    def test_success_criteria_mentions_enterprise_discount(self, contract):
        text = " ".join(contract.success_criteria)
        assert "ENTERPRISE_DISCOUNT" in text

    def test_success_criteria_mentions_loyalty(self, contract):
        text = " ".join(contract.success_criteria)
        assert "LOYALTY" in text

    def test_success_criteria_mentions_tests(self, contract):
        text = " ".join(contract.success_criteria)
        assert "test" in text.lower()
