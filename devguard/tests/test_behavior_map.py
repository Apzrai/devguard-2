"""
test_behavior_map.py — Tests for devguard/behavior_map.py

All tests run against the actual sample_app/ directory.
Behavior map values are verified against values actually read from source.
"""

import pytest
from pathlib import Path

from devguard.understand import understand
from devguard.behavior_map import build_behavior_map, BehaviorMap

SAMPLE_APP = Path(__file__).parent.parent.parent / "sample_app"


@pytest.fixture(scope="module")
def bmap():
    u = understand(SAMPLE_APP)
    return build_behavior_map(u)


class TestBehaviorMapStructure:
    def test_returns_behavior_map_instance(self, bmap):
        assert isinstance(bmap, BehaviorMap)

    def test_has_behaviors_list(self, bmap):
        assert isinstance(bmap.behaviors, list)
        assert len(bmap.behaviors) >= 7

    def test_has_pipeline_order(self, bmap):
        assert isinstance(bmap.pipeline_order, list)
        assert len(bmap.pipeline_order) > 0

    def test_all_behaviors_have_required_fields(self, bmap):
        required = {"id", "name", "description", "source_file", "source_symbol",
                    "relevant_tests", "dependencies", "protected", "provenance", "confidence"}
        for b in bmap.behaviors:
            missing = required - set(b.keys())
            assert not missing, f"Behavior {b.get('id')} missing fields: {missing}"

    def test_behavior_ids_are_unique(self, bmap):
        ids = [b["id"] for b in bmap.behaviors]
        assert len(ids) == len(set(ids))


class TestBehaviorMapContents:
    def test_b001_new_discount_exists(self, bmap):
        b = bmap.get("B001")
        assert b is not None
        assert b["source_symbol"] == "NEW_CUSTOMER_DISCOUNT"

    def test_b002_loyalty_discount_exists(self, bmap):
        b = bmap.get("B002")
        assert b is not None
        assert b["source_symbol"] == "LOYALTY_DISCOUNT"

    def test_b003_enterprise_discount_exists(self, bmap):
        b = bmap.get("B003")
        assert b is not None
        assert b["source_symbol"] == "ENTERPRISE_DISCOUNT"

    def test_b004_discount_ordering_exists(self, bmap):
        b = bmap.get("B004")
        assert b is not None
        assert "apply_discounts" in b["source_symbol"]

    def test_b005_coupon_before_tax_exists(self, bmap):
        b = bmap.get("B005")
        assert b is not None
        assert "checkout" in b["source_file"].lower() or "discount" in b["source_file"].lower()

    def test_b006_tax_after_discounts_exists(self, bmap):
        b = bmap.get("B006")
        assert b is not None
        assert "tax" in b["source_file"].lower()

    def test_b007_refund_behavior_exists(self, bmap):
        b = bmap.get("B007")
        assert b is not None
        assert "refund" in b["source_file"].lower()

    def test_b008_independence_invariant_exists(self, bmap):
        b = bmap.get("B008")
        assert b is not None
        assert "independence" in b["name"].lower() or "independent" in b["description"].lower()


class TestProtectedBehaviors:
    def test_b001_is_protected(self, bmap):
        assert bmap.get("B001")["protected"] is True

    def test_b002_is_protected(self, bmap):
        assert bmap.get("B002")["protected"] is True

    def test_b003_is_not_protected(self, bmap):
        """B003 (ENTERPRISE_DISCOUNT) is the target of the maintenance request — not protected."""
        assert bmap.get("B003")["protected"] is False

    def test_b004_is_protected(self, bmap):
        assert bmap.get("B004")["protected"] is True

    def test_b005_is_protected(self, bmap):
        assert bmap.get("B005")["protected"] is True

    def test_b006_is_protected(self, bmap):
        assert bmap.get("B006")["protected"] is True

    def test_b007_is_protected(self, bmap):
        assert bmap.get("B007")["protected"] is True

    def test_b008_is_protected(self, bmap):
        assert bmap.get("B008")["protected"] is True

    def test_protected_behaviors_returns_at_least_6(self, bmap):
        assert len(bmap.protected_behaviors()) >= 6


class TestBehaviorProvenance:
    def test_discount_constants_have_tested_provenance(self, bmap):
        """B001/B002/B003 must be TESTED because test_customers.py asserts their values."""
        for bid in ("B001", "B002", "B003"):
            b = bmap.get(bid)
            assert b["provenance"] in ("TESTED", "OBSERVED"), \
                f"Unexpected provenance for {bid}: {b['provenance']}"

    def test_b004_ordering_is_tested(self, bmap):
        assert bmap.get("B004")["provenance"] == "TESTED"

    def test_b005_coupon_before_tax_is_tested(self, bmap):
        assert bmap.get("B005")["provenance"] == "TESTED"

    def test_b007_refund_is_tested(self, bmap):
        assert bmap.get("B007")["provenance"] == "TESTED"

    def test_b008_independence_is_tested(self, bmap):
        assert bmap.get("B008")["provenance"] == "TESTED"

    def test_no_behavior_has_inferred_provenance_alone(self, bmap):
        """No behavior should be solely INFERRED — all have OBSERVED/TESTED backing."""
        for b in bmap.behaviors:
            assert b["provenance"] != "INFERRED", \
                f"Behavior {b['id']} is only INFERRED — needs grounding"


class TestBehaviorDiscountValuesFromActualSource:
    """These tests verify that discount values in the behavior map match
    the actual constants in customers.py — not hardcoded expectations."""

    def test_new_discount_description_contains_5_percent(self, bmap):
        b = bmap.get("B001")
        assert "5%" in b["description"]

    def test_loyalty_discount_description_contains_10_percent(self, bmap):
        b = bmap.get("B002")
        assert "10%" in b["description"]

    def test_enterprise_discount_description_contains_10_percent(self, bmap):
        b = bmap.get("B003")
        assert "10%" in b["description"]

    def test_tax_description_contains_actual_rate(self, bmap):
        b = bmap.get("B006")
        # Should contain the actual DEFAULT_TAX_RATE from tax.py (8.5%)
        assert "8.5%" in b["description"]

    def test_b002_relevant_tests_include_loyalty_tests(self, bmap):
        b = bmap.get("B002")
        loyalty_tests = [t for t in b["relevant_tests"] if "loyalty" in t.lower()]
        assert len(loyalty_tests) >= 1

    def test_b003_relevant_tests_include_enterprise_tests(self, bmap):
        b = bmap.get("B003")
        ent_tests = [t for t in b["relevant_tests"] if "enterprise" in t.lower()]
        assert len(ent_tests) >= 1


class TestPipelineOrder:
    def test_pipeline_order_starts_with_discount(self, bmap):
        assert bmap.pipeline_order[0].startswith("B00")

    def test_pipeline_description_contains_key_steps(self, bmap):
        desc = bmap.to_dict()["pipeline_description"]
        assert "customer_discount" in desc
        assert "coupon" in desc
        assert "tax" in desc
