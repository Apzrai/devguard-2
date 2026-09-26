"""
test_impact.py — Tests for devguard/impact.py
"""

import pytest
from pathlib import Path

from devguard.understand import understand
from devguard.behavior_map import build_behavior_map
from devguard.contract import build_contract, make_enterprise_discount_request
from devguard.impact import analyze_impact, ImpactAnalysis

SAMPLE_APP = Path(__file__).parent.parent.parent / "sample_app"


@pytest.fixture(scope="module")
def impact():
    u = understand(SAMPLE_APP)
    bmap = build_behavior_map(u)
    contract = build_contract(bmap, make_enterprise_discount_request())
    return analyze_impact(u, bmap, contract)


class TestImpactAnalysisStructure:
    def test_returns_impact_analysis_instance(self, impact):
        assert isinstance(impact, ImpactAnalysis)

    def test_has_impact_id(self, impact):
        assert len(impact.to_dict()["impact_id"]) == 36

    def test_has_analyzed_at(self, impact):
        assert "T" in impact.to_dict()["analyzed_at"]

    def test_has_contract_id(self, impact):
        assert len(impact.to_dict()["contract_id"]) == 36

    def test_target_change_is_enterprise_discount(self, impact):
        tc = impact.to_dict()["target_change"]
        assert tc["symbol"] == "ENTERPRISE_DISCOUNT"
        assert tc["file"] == "customers.py"


class TestDirectlyAffected:
    def test_customers_py_is_directly_affected(self, impact):
        files = {Path(d["file"]).name for d in impact.directly_affected}
        assert "customers.py" in files

    def test_directly_affected_has_defines_target_relationship(self, impact):
        for d in impact.directly_affected:
            assert d["relationship"] == "defines_target"

    def test_directly_affected_provenance_is_observed(self, impact):
        for d in impact.directly_affected:
            assert d["provenance"] == "OBSERVED"

    def test_directly_affected_does_not_include_unrelated_files(self, impact):
        files = {Path(d["file"]).name for d in impact.directly_affected}
        # Only customers.py defines ENTERPRISE_DISCOUNT
        assert "tax.py" not in files
        assert "discount.py" not in files
        assert "refunds.py" not in files


class TestIndirectlyAffected:
    def test_checkout_py_is_indirectly_affected(self, impact):
        """checkout.py imports from customers — it will see the new discount rate."""
        files = {Path(d["file"]).name for d in impact.indirectly_affected}
        assert "checkout.py" in files

    def test_indirectly_affected_has_imports_target_relationship(self, impact):
        for d in impact.indirectly_affected:
            assert d["relationship"] == "imports_target"

    def test_indirectly_affected_provenance_is_observed(self, impact):
        for d in impact.indirectly_affected:
            assert d["provenance"] == "OBSERVED"

    def test_indirectly_affected_does_not_include_customers_py(self, impact):
        """customers.py is directly affected, not indirectly."""
        files = {Path(d["file"]).name for d in impact.indirectly_affected}
        assert "customers.py" not in files


class TestProtectedFiles:
    def test_customers_py_in_protected_files(self, impact):
        files = {Path(p["file"]).name for p in impact.to_dict()["protected_files"]}
        assert "customers.py" in files

    def test_discount_py_in_protected_files(self, impact):
        files = {Path(p["file"]).name for p in impact.to_dict()["protected_files"]}
        assert "discount.py" in files

    def test_each_protected_file_has_severity(self, impact):
        for pf in impact.to_dict()["protected_files"]:
            assert pf["severity"] in {"CRITICAL", "HIGH", "LOW"}

    def test_each_protected_file_has_must_not(self, impact):
        for pf in impact.to_dict()["protected_files"]:
            assert len(pf["must_not"]) > 0


class TestAtRiskTests:
    def test_at_risk_tests_is_non_empty(self, impact):
        assert len(impact.at_risk_tests) > 0

    def test_loyalty_related_tests_are_at_high_risk(self, impact):
        high_risk = [t for t in impact.at_risk_tests if t["risk_level"] == "HIGH"]
        high_risk_fns = [t["test_function"] for t in high_risk]
        # At least one loyalty test must be flagged high risk
        loyalty_tests = [fn for fn in high_risk_fns if "loyalty" in fn.lower()]
        assert len(loyalty_tests) >= 1, \
            f"Expected loyalty tests in high-risk, got: {high_risk_fns}"

    def test_independence_test_is_at_high_risk(self, impact):
        high_risk_fns = {t["test_function"] for t in impact.at_risk_tests if t["risk_level"] == "HIGH"}
        independence = [fn for fn in high_risk_fns if "independen" in fn.lower()]
        assert len(independence) >= 1, \
            f"Expected independence/independent test in high-risk, got: {sorted(high_risk_fns)}"

    def test_all_at_risk_tests_have_contract_clause(self, impact):
        for t in impact.at_risk_tests:
            assert t["contract_clause"] is not None

    def test_all_at_risk_tests_have_risk_level(self, impact):
        for t in impact.at_risk_tests:
            assert t["risk_level"] in {"HIGH", "MEDIUM", "LOW"}

    def test_all_at_risk_tests_have_test_file(self, impact):
        for t in impact.at_risk_tests:
            assert t["test_file"] != "unknown", \
                f"Test function {t['test_function']} could not be resolved to a file"


class TestRiskAssessment:
    def test_safe_to_change_is_true_for_scoped_request(self, impact):
        """The scoped request (ENTERPRISE_DISCOUNT only) should be assessed safe."""
        assert impact.safe_to_change is True

    def test_risk_summary_mentions_target_symbol(self, impact):
        assert "ENTERPRISE_DISCOUNT" in impact.risk_summary

    def test_risk_summary_mentions_loyalty(self, impact):
        assert "LOYALTY" in impact.risk_summary

    def test_risk_summary_mentions_high_risk_count(self, impact):
        # The summary should communicate how many high-risk tests there are
        assert "high-risk" in impact.risk_summary.lower()
