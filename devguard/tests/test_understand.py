"""
test_understand.py — Tests for devguard/understand.py

All tests run against the actual sample_app/ directory.
No mocking, no fabricated data.
"""

import pytest
from pathlib import Path

from devguard.understand import understand, ProjectUnderstanding

# Resolve sample_app relative to the workspace root
SAMPLE_APP = Path(__file__).parent.parent.parent / "sample_app"


@pytest.fixture(scope="module")
def understanding():
    """Run understand() once and share the result across all tests in this module."""
    return understand(SAMPLE_APP)


class TestUnderstandProducesData:
    def test_returns_project_understanding_instance(self, understanding):
        assert isinstance(understanding, ProjectUnderstanding)

    def test_project_root_is_set(self, understanding):
        assert "sample_app" in understanding.to_dict()["project_root"]

    def test_analyzed_at_is_iso8601(self, understanding):
        ts = understanding.to_dict()["analyzed_at"]
        assert "T" in ts and "Z" in ts or "+" in ts

    def test_provenance_is_observed(self, understanding):
        assert understanding.to_dict()["provenance"] == "OBSERVED"


class TestSourceFiles:
    def test_expected_source_files_present(self, understanding):
        paths = {Path(sf["path"]).name for sf in understanding.source_files}
        for expected in ["catalog.py", "cart.py", "checkout.py",
                         "customers.py", "discount.py", "tax.py", "refunds.py"]:
            assert expected in paths, f"Missing source file: {expected}"

    def test_each_source_file_has_sha256(self, understanding):
        for sf in understanding.source_files:
            assert len(sf["sha256"]) == 64
            assert sf["sha256"].isalnum()

    def test_customers_file_has_classes_and_functions(self, understanding):
        sf = understanding.get_source_file("customers.py")
        assert sf is not None
        assert "CustomerType" in sf["classes"]
        assert "get_customer_discount_rate" in sf["functions"]

    def test_discount_file_has_apply_discounts_function(self, understanding):
        sf = understanding.get_source_file("discount.py")
        assert sf is not None
        assert "apply_discounts" in sf["functions"]

    def test_tax_file_has_tax_calculator_class(self, understanding):
        sf = understanding.get_source_file("tax.py")
        assert sf is not None
        assert "TaxCalculator" in sf["classes"]

    def test_all_source_files_have_line_count(self, understanding):
        for sf in understanding.source_files:
            assert sf["line_count"] > 0

    def test_all_source_files_have_provenance_observed(self, understanding):
        for sf in understanding.source_files:
            assert sf["provenance"] == "OBSERVED"


class TestConstants:
    def test_new_customer_discount_constant_found(self, understanding):
        consts = understanding.get_constants_by_file("customers.py")
        names = [c["name"] for c in consts]
        assert "NEW_CUSTOMER_DISCOUNT" in names

    def test_loyalty_discount_constant_found(self, understanding):
        consts = understanding.get_constants_by_file("customers.py")
        names = [c["name"] for c in consts]
        assert "LOYALTY_DISCOUNT" in names

    def test_enterprise_discount_constant_found(self, understanding):
        consts = understanding.get_constants_by_file("customers.py")
        names = [c["name"] for c in consts]
        assert "ENTERPRISE_DISCOUNT" in names

    def test_discount_constants_are_three_independent_entries(self, understanding):
        consts = understanding.get_constants_by_file("customers.py")
        discount_consts = [c for c in consts if "DISCOUNT" in c["name"]]
        assert len(discount_consts) == 3

    def test_new_customer_discount_value_is_0_05(self, understanding):
        consts = understanding.get_constants_by_file("customers.py")
        val = next(c["value_repr"] for c in consts if c["name"] == "NEW_CUSTOMER_DISCOUNT")
        assert float(eval(val)) == pytest.approx(0.05)

    def test_loyalty_discount_value_is_0_10(self, understanding):
        consts = understanding.get_constants_by_file("customers.py")
        val = next(c["value_repr"] for c in consts if c["name"] == "LOYALTY_DISCOUNT")
        assert float(eval(val)) == pytest.approx(0.10)

    def test_enterprise_discount_value_is_0_10(self, understanding):
        consts = understanding.get_constants_by_file("customers.py")
        val = next(c["value_repr"] for c in consts if c["name"] == "ENTERPRISE_DISCOUNT")
        assert float(eval(val)) == pytest.approx(0.10)

    def test_default_tax_rate_constant_found(self, understanding):
        consts = understanding.get_constants_by_file("tax.py")
        names = [c["name"] for c in consts]
        assert "DEFAULT_TAX_RATE" in names

    def test_default_tax_rate_value_is_0_085(self, understanding):
        consts = understanding.get_constants_by_file("tax.py")
        val = next(c["value_repr"] for c in consts if c["name"] == "DEFAULT_TAX_RATE")
        assert float(eval(val)) == pytest.approx(0.085)

    def test_all_constants_have_provenance_observed(self, understanding):
        for c in understanding.constants:
            assert c["provenance"] == "OBSERVED"

    def test_all_constants_have_lineno(self, understanding):
        for c in understanding.constants:
            assert c["lineno"] > 0


class TestTestFiles:
    def test_expected_test_files_present(self, understanding):
        paths = {Path(tf["path"]).name for tf in understanding.test_files}
        for expected in ["test_customers.py", "test_discount.py", "test_checkout.py",
                         "test_tax.py", "test_cart.py", "test_refunds.py"]:
            assert expected in paths, f"Missing test file: {expected}"

    def test_each_test_file_has_test_functions(self, understanding):
        for tf in understanding.test_files:
            assert tf["test_count"] > 0, f"{tf['path']} has no test functions"

    def test_test_customers_has_independence_test(self, understanding):
        fns = understanding.get_tests_for_file("customers.py")
        assert "test_discount_rates_are_independent" in fns

    def test_test_customers_has_loyalty_test(self, understanding):
        fns = understanding.get_tests_for_file("customers.py")
        assert "test_loyalty_discount_is_10_percent" in fns

    def test_test_customers_has_enterprise_test(self, understanding):
        fns = understanding.get_tests_for_file("customers.py")
        assert "test_enterprise_discount_is_10_percent" in fns

    def test_total_test_count_is_reasonable(self, understanding):
        total = sum(tf["test_count"] for tf in understanding.test_files)
        assert total >= 100  # we know there are 126


class TestDocFiles:
    def test_business_rules_doc_found(self, understanding):
        paths = {Path(df["path"]).name for df in understanding.doc_files}
        assert "BUSINESS_RULES.md" in paths

    def test_doc_files_have_sha256(self, understanding):
        for df in understanding.doc_files:
            assert len(df["sha256"]) == 64

    def test_doc_files_have_provenance_documented(self, understanding):
        for df in understanding.doc_files:
            assert df["provenance"] == "DOCUMENTED"


class TestConvenienceMethods:
    def test_get_source_file_returns_none_for_unknown(self, understanding):
        assert understanding.get_source_file("nonexistent.py") is None

    def test_get_tests_for_file_returns_list(self, understanding):
        result = understanding.get_tests_for_file("customers.py")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_get_tests_for_unknown_file_returns_empty(self, understanding):
        assert understanding.get_tests_for_file("unknown.py") == []

    def test_invalid_project_root_raises(self):
        with pytest.raises(ValueError, match="not a directory"):
            understand("/nonexistent/path/xyz")
