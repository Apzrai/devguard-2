"""
test_discount.py — Tests for the discount and coupon application logic.

Business rules under test:
  1. Customer discount is applied to the raw subtotal.
  2. Coupon discount is applied AFTER customer discount (to the reduced amount).
  3. Tax is NOT applied here — that is tax.py's responsibility.
  4. A coupon cannot reduce the payable amount below zero.
  5. An expired coupon raises ValueError.
  6. Percentage and fixed-amount coupons both work correctly.
"""

import pytest
from datetime import date

from sample_app.discount import (
    Coupon,
    CouponRegistry,
    CouponType,
    apply_customer_discount,
    apply_coupon,
    apply_discounts,
)


# ---------------------------------------------------------------------------
# apply_customer_discount()
# ---------------------------------------------------------------------------

class TestApplyCustomerDiscount:
    def test_no_discount(self):
        assert apply_customer_discount(100.00, 0.0) == 100.00

    def test_5_percent_discount(self):
        assert apply_customer_discount(100.00, 0.05) == 95.00

    def test_10_percent_discount(self):
        assert apply_customer_discount(100.00, 0.10) == 90.00

    def test_100_percent_discount(self):
        assert apply_customer_discount(100.00, 1.0) == 0.00

    def test_fractional_result_rounded_to_2dp(self):
        # $99.99 × (1 - 0.10) = 89.991 → 89.99
        assert apply_customer_discount(99.99, 0.10) == 89.99

    def test_invalid_rate_above_1_raises(self):
        with pytest.raises(ValueError, match="discount_rate"):
            apply_customer_discount(100.00, 1.1)

    def test_invalid_rate_below_0_raises(self):
        with pytest.raises(ValueError, match="discount_rate"):
            apply_customer_discount(100.00, -0.01)


# ---------------------------------------------------------------------------
# apply_coupon()
# ---------------------------------------------------------------------------

class TestApplyCoupon:
    def test_fixed_coupon_reduces_amount(self):
        coupon = Coupon("SAVE10", CouponType.FIXED, 10.00)
        assert apply_coupon(90.00, coupon) == 80.00

    def test_percentage_coupon_reduces_amount(self):
        coupon = Coupon("PCTOFF", CouponType.PERCENTAGE, 0.10)
        # 90.00 × 0.90 = 81.00
        assert apply_coupon(90.00, coupon) == 81.00

    def test_fixed_coupon_floors_at_zero(self):
        coupon = Coupon("BIGDEAL", CouponType.FIXED, 200.00)
        assert apply_coupon(50.00, coupon) == 0.00

    def test_percentage_coupon_floors_at_zero(self):
        # 100% off should not go negative
        coupon = Coupon("FREE", CouponType.PERCENTAGE, 1.0)
        assert apply_coupon(50.00, coupon) == 0.00

    def test_expired_coupon_raises(self):
        coupon = Coupon("OLD", CouponType.FIXED, 5.00, expires_on=date(2000, 1, 1))
        with pytest.raises(ValueError, match="expired"):
            apply_coupon(100.00, coupon)

    def test_valid_coupon_with_future_expiry(self):
        coupon = Coupon("FUTURE", CouponType.FIXED, 5.00, expires_on=date(2099, 12, 31))
        assert apply_coupon(100.00, coupon) == 95.00

    def test_coupon_valid_on_expiry_date(self):
        today = date.today()
        coupon = Coupon("TODAY", CouponType.FIXED, 5.00, expires_on=today)
        result = apply_coupon(100.00, coupon, as_of=today)
        assert result == 95.00

    def test_coupon_invalid_day_after_expiry(self):
        from datetime import timedelta
        yesterday = date.today() - timedelta(days=1)
        coupon = Coupon("YEST", CouponType.FIXED, 5.00, expires_on=yesterday)
        with pytest.raises(ValueError, match="expired"):
            apply_coupon(100.00, coupon)


# ---------------------------------------------------------------------------
# apply_discounts() — full chain
# ---------------------------------------------------------------------------

class TestApplyDiscounts:
    def test_customer_discount_only(self):
        result = apply_discounts(subtotal=100.00, discount_rate=0.10)
        assert result["subtotal"] == 100.00
        assert result["after_customer_discount"] == 90.00
        assert result["after_coupon"] == 90.00
        assert result["customer_discount_amount"] == 10.00
        assert result["coupon_discount_amount"] == 0.00
        assert result["total_discount_amount"] == 10.00

    def test_coupon_applied_after_customer_discount(self):
        """
        Business rule: coupon is applied to the post-customer-discount amount.

        $100 subtotal
        - 10% customer discount → $90.00
        - $10 fixed coupon applied to $90.00 → $80.00
        NOT: $10 coupon applied to $100 first (which would be wrong).
        """
        coupon = Coupon("SAVE10", CouponType.FIXED, 10.00)
        result = apply_discounts(subtotal=100.00, discount_rate=0.10, coupon=coupon)
        assert result["after_customer_discount"] == 90.00
        assert result["coupon_discount_amount"] == 10.00
        assert result["after_coupon"] == 80.00
        assert result["total_discount_amount"] == 20.00

    def test_percentage_coupon_after_customer_discount(self):
        """
        $200 subtotal
        - 5% customer discount → $190.00
        - 15% coupon on $190.00 → $190 × 0.85 = $161.50
        """
        coupon = Coupon("SUMMER15", CouponType.PERCENTAGE, 0.15)
        result = apply_discounts(subtotal=200.00, discount_rate=0.05, coupon=coupon)
        assert result["after_customer_discount"] == 190.00
        assert result["after_coupon"] == pytest.approx(161.50)

    def test_no_discount_no_coupon(self):
        result = apply_discounts(subtotal=50.00, discount_rate=0.00)
        assert result["after_coupon"] == 50.00
        assert result["total_discount_amount"] == 0.00

    def test_ordering_customer_then_coupon_not_reversed(self):
        """
        Confirm the order: customer discount first, then coupon.
        If order were reversed, the coupon would reduce the base
        before the customer discount, yielding a different number.
        """
        coupon = Coupon("SAVE20", CouponType.FIXED, 20.00)
        result = apply_discounts(subtotal=100.00, discount_rate=0.10, coupon=coupon)
        # Correct order: 100 → 90 (customer) → 70 (coupon)
        assert result["after_coupon"] == 70.00
        # Wrong order would be: 100 → 80 (coupon) → 72 (customer) — NOT this


# ---------------------------------------------------------------------------
# Coupon registry
# ---------------------------------------------------------------------------

class TestCouponRegistry:
    def test_get_known_code(self):
        registry = CouponRegistry()
        coupon = registry.get("SAVE10")
        assert coupon is not None
        assert coupon.value == 10.00

    def test_get_unknown_code_returns_none(self):
        registry = CouponRegistry()
        assert registry.get("UNKNOWN") is None

    def test_get_or_raise_unknown_raises(self):
        registry = CouponRegistry()
        with pytest.raises(KeyError, match="UNKNOWN"):
            registry.get_or_raise("UNKNOWN")

    def test_code_lookup_case_insensitive(self):
        registry = CouponRegistry()
        assert registry.get("save10") is not None

    def test_percentage_coupon_value_above_1_rejected(self):
        with pytest.raises(ValueError, match="Percentage coupon value"):
            Coupon("BAD", CouponType.PERCENTAGE, 1.5)
