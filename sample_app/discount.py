"""
discount.py — Discount and coupon application logic for LegacyShop.

Application order (enforced here):
  1. Customer discount   — applied to the raw subtotal
  2. Coupon discount     — applied to the post-customer-discount subtotal
  3. Tax                 — calculated separately (see tax.py) on the result

Both discounts are reductions on a running amount; they never stack multiplicatively
against each other's base — each step works on the running total left by the previous.

Coupons:
  - Fixed-amount coupons reduce the total by a flat dollar value.
  - Percentage coupons reduce the total by a percentage.
  - A coupon cannot reduce the payable amount below zero.
  - Expired coupons are rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional


class CouponType(str, Enum):
    FIXED = "FIXED"           # flat dollar amount off
    PERCENTAGE = "PERCENTAGE" # percentage off


@dataclass
class Coupon:
    """A discount coupon that can be applied to an order."""

    code: str
    coupon_type: CouponType
    value: float              # dollar amount or fraction (0.0–1.0) depending on type
    expires_on: Optional[date] = None   # None means never expires

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError(f"Coupon value must be >= 0, got {self.value}")
        if self.coupon_type == CouponType.PERCENTAGE and self.value > 1.0:
            raise ValueError(
                f"Percentage coupon value must be in [0.0, 1.0], got {self.value}"
            )

    def is_valid(self, as_of: Optional[date] = None) -> bool:
        """Return True if the coupon is not expired relative to as_of (defaults to today)."""
        if self.expires_on is None:
            return True
        check_date = as_of or date.today()
        return check_date <= self.expires_on


# ---------------------------------------------------------------------------
# Default coupon registry (in-memory)
# ---------------------------------------------------------------------------

_DEFAULT_COUPONS: dict[str, Coupon] = {
    "SAVE10":    Coupon("SAVE10",    CouponType.FIXED,      10.00),
    "SAVE20":    Coupon("SAVE20",    CouponType.FIXED,      20.00),
    "SUMMER15":  Coupon("SUMMER15",  CouponType.PERCENTAGE,  0.15),
    "WELCOME5":  Coupon("WELCOME5",  CouponType.PERCENTAGE,  0.05),
}


class CouponRegistry:
    """Look up and validate coupon codes."""

    def __init__(self, coupons: Optional[dict[str, Coupon]] = None) -> None:
        self._coupons = coupons if coupons is not None else dict(_DEFAULT_COUPONS)

    def get(self, code: str) -> Optional[Coupon]:
        return self._coupons.get(code.upper())

    def get_or_raise(self, code: str) -> Coupon:
        coupon = self.get(code)
        if coupon is None:
            raise KeyError(f"Unknown coupon code: {code!r}")
        return coupon


# ---------------------------------------------------------------------------
# Discount application functions
# ---------------------------------------------------------------------------

def apply_customer_discount(subtotal: float, discount_rate: float) -> float:
    """Apply a customer discount rate to a subtotal.

    Args:
        subtotal:      The raw cart subtotal (sum of line prices).
        discount_rate: Fraction in [0.0, 1.0].  0.10 means 10% off.

    Returns:
        Amount after customer discount.
    """
    if not (0.0 <= discount_rate <= 1.0):
        raise ValueError(f"discount_rate must be in [0.0, 1.0], got {discount_rate}")
    return round(subtotal * (1.0 - discount_rate), 2)


def apply_coupon(amount: float, coupon: Coupon, as_of: Optional[date] = None) -> float:
    """Apply a coupon to an already-discounted amount.

    Args:
        amount: The subtotal after customer discount.
        coupon: The Coupon object to apply.
        as_of:  Date to check coupon validity against (defaults to today).

    Returns:
        Amount after coupon, floored at 0.0.

    Raises:
        ValueError: If the coupon is expired.
    """
    if not coupon.is_valid(as_of):
        raise ValueError(f"Coupon {coupon.code!r} is expired")

    if coupon.coupon_type == CouponType.FIXED:
        result = amount - coupon.value
    else:  # PERCENTAGE
        result = amount * (1.0 - coupon.value)

    return round(max(result, 0.0), 2)


def apply_discounts(
    subtotal: float,
    discount_rate: float,
    coupon: Optional[Coupon] = None,
    as_of: Optional[date] = None,
) -> dict:
    """Apply the full discount chain and return a breakdown.

    Order: customer discount → coupon → (tax handled separately in tax.py)

    Returns a dict with:
        subtotal:            original input
        after_customer_discount: subtotal after customer discount
        after_coupon:        after coupon (equals after_customer_discount if no coupon)
        customer_discount_amount: dollar amount saved by customer discount
        coupon_discount_amount:   dollar amount saved by coupon
        total_discount_amount:    combined dollar savings
    """
    after_customer = apply_customer_discount(subtotal, discount_rate)
    customer_saving = round(subtotal - after_customer, 2)

    if coupon is not None:
        after_coupon = apply_coupon(after_customer, coupon, as_of)
        coupon_saving = round(after_customer - after_coupon, 2)
    else:
        after_coupon = after_customer
        coupon_saving = 0.0

    return {
        "subtotal": subtotal,
        "after_customer_discount": after_customer,
        "after_coupon": after_coupon,
        "customer_discount_amount": customer_saving,
        "coupon_discount_amount": coupon_saving,
        "total_discount_amount": round(customer_saving + coupon_saving, 2),
    }
