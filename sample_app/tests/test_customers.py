"""
test_customers.py — Tests for customer types and discount rates.

These tests are the behavioral ground truth for the customer discount contract.
Any change to discount rates will cause tests here to fail, making it detectable
by DEVGUARD's verification step.
"""

import pytest
from sample_app.customers import (
    Customer,
    CustomerType,
    NEW_CUSTOMER_DISCOUNT,
    LOYALTY_DISCOUNT,
    ENTERPRISE_DISCOUNT,
    get_customer_discount_rate,
)


# ---------------------------------------------------------------------------
# Discount rate constant tests
# These are the PRIMARY behavioral contract anchors.
# ---------------------------------------------------------------------------

class TestDiscountRateConstants:
    def test_new_customer_discount_is_5_percent(self):
        assert NEW_CUSTOMER_DISCOUNT == 0.05

    def test_loyalty_discount_is_10_percent(self):
        assert LOYALTY_DISCOUNT == 0.10

    def test_enterprise_discount_is_10_percent(self):
        assert ENTERPRISE_DISCOUNT == 0.10

    def test_discount_rates_are_independent(self):
        """Enterprise and Loyalty rates are separate constants.

        This is the key DEVGUARD controlled-failure invariant:
        changing ENTERPRISE_DISCOUNT must NOT change LOYALTY_DISCOUNT.
        """
        assert ENTERPRISE_DISCOUNT != NEW_CUSTOMER_DISCOUNT
        # Both happen to be 0.10, but they are independent constants.
        # A change to one must not affect the other.
        assert LOYALTY_DISCOUNT == 0.10
        assert ENTERPRISE_DISCOUNT == 0.10


# ---------------------------------------------------------------------------
# get_customer_discount_rate()
# ---------------------------------------------------------------------------

class TestGetCustomerDiscountRate:
    def test_new_customer_rate(self):
        assert get_customer_discount_rate(CustomerType.NEW) == 0.05

    def test_loyalty_customer_rate(self):
        assert get_customer_discount_rate(CustomerType.LOYALTY) == 0.10

    def test_enterprise_customer_rate(self):
        assert get_customer_discount_rate(CustomerType.ENTERPRISE) == 0.10

    def test_loyalty_rate_equals_10_percent_exactly(self):
        rate = get_customer_discount_rate(CustomerType.LOYALTY)
        assert rate == pytest.approx(0.10)

    def test_enterprise_rate_equals_10_percent_exactly(self):
        rate = get_customer_discount_rate(CustomerType.ENTERPRISE)
        assert rate == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# Customer model
# ---------------------------------------------------------------------------

class TestCustomerModel:
    def test_new_customer_has_correct_discount(self):
        c = Customer("C001", "Alice", "alice@example.com", CustomerType.NEW)
        assert c.discount_rate == 0.05

    def test_loyalty_customer_has_correct_discount(self):
        c = Customer("C002", "Bob", "bob@example.com", CustomerType.LOYALTY)
        assert c.discount_rate == 0.10

    def test_enterprise_customer_uses_global_rate_by_default(self):
        c = Customer("C003", "Acme Corp", "acme@example.com", CustomerType.ENTERPRISE)
        assert c.discount_rate == ENTERPRISE_DISCOUNT

    def test_enterprise_customer_with_contract_rate_overrides_global(self):
        c = Customer(
            "C004", "BigCorp", "big@example.com",
            CustomerType.ENTERPRISE,
            contract_discount_rate=0.20,
        )
        assert c.discount_rate == 0.20

    def test_non_enterprise_cannot_have_contract_rate(self):
        with pytest.raises(ValueError, match="ENTERPRISE"):
            Customer(
                "C005", "Dave", "dave@example.com",
                CustomerType.LOYALTY,
                contract_discount_rate=0.15,
            )

    def test_contract_rate_out_of_range_rejected(self):
        with pytest.raises(ValueError, match="contract_discount_rate"):
            Customer(
                "C006", "E Corp", "e@example.com",
                CustomerType.ENTERPRISE,
                contract_discount_rate=1.5,
            )


# ---------------------------------------------------------------------------
# Independence tests — the core DEVGUARD failure scenario anchors
# ---------------------------------------------------------------------------

class TestDiscountIndependence:
    """Verify that New, Loyalty, and Enterprise discounts are independent.

    These tests MUST FAIL if someone accidentally changes the wrong constant.
    """

    def test_loyalty_discount_unchanged_when_enterprise_is_at_default(self):
        loyalty_rate = get_customer_discount_rate(CustomerType.LOYALTY)
        enterprise_rate = get_customer_discount_rate(CustomerType.ENTERPRISE)
        # Assert exact values — do not change either without updating the contract
        assert loyalty_rate == 0.10
        assert enterprise_rate == 0.10

    def test_new_customer_discount_unchanged(self):
        assert get_customer_discount_rate(CustomerType.NEW) == 0.05

    def test_loyalty_customer_100_dollar_order_discount(self):
        """Loyalty customer: 10% off $100.00 → $90.00 after discount."""
        c = Customer("C010", "Loyal", "l@x.com", CustomerType.LOYALTY)
        discounted = round(100.00 * (1.0 - c.discount_rate), 2)
        assert discounted == 90.00

    def test_enterprise_customer_100_dollar_order_discount(self):
        """Enterprise customer: 10% off $100.00 → $90.00 after discount."""
        c = Customer("C011", "Corp", "corp@x.com", CustomerType.ENTERPRISE)
        discounted = round(100.00 * (1.0 - c.discount_rate), 2)
        assert discounted == 90.00

    def test_new_customer_100_dollar_order_discount(self):
        """New customer: 5% off $100.00 → $95.00 after discount."""
        c = Customer("C012", "New", "new@x.com", CustomerType.NEW)
        discounted = round(100.00 * (1.0 - c.discount_rate), 2)
        assert discounted == 95.00
