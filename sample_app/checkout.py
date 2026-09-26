"""
checkout.py — Order placement and checkout pipeline for LegacyShop.

Responsibilities:
  1. Validate cart is not empty.
  2. Validate stock availability for every line item.
  3. Apply customer discount → coupon → tax (in that order).
  4. Reserve stock in the catalog.
  5. Produce an Order record with a full pricing breakdown.

The Order record is immutable after creation and serves as the source of truth
for the refund flow.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from sample_app.cart import Cart, CartLine
from sample_app.catalog import Catalog
from sample_app.customers import Customer
from sample_app.discount import CouponRegistry, apply_discounts, Coupon
from sample_app.tax import TaxCalculator


# ---------------------------------------------------------------------------
# Order data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OrderLine:
    """Immutable snapshot of a cart line at the time of checkout."""
    sku: str
    name: str
    unit_price: float
    quantity: int
    line_total: float   # unit_price × quantity


@dataclass(frozen=True)
class Order:
    """Immutable order record produced by checkout."""

    order_id: str
    customer_id: str
    customer_type: str
    placed_at: str                  # ISO-8601 UTC timestamp

    lines: tuple                    # tuple of OrderLine (frozen)

    # Pricing breakdown
    subtotal: float                 # raw sum of line totals
    customer_discount_rate: float   # e.g. 0.10
    customer_discount_amount: float
    after_customer_discount: float

    coupon_code: Optional[str]
    coupon_discount_amount: float
    after_coupon: float             # taxable base

    tax_rate: float
    tax_amount: float
    grand_total: float              # what the customer pays

    @property
    def taxable_amount(self) -> float:
        return self.after_coupon


# ---------------------------------------------------------------------------
# CheckoutService
# ---------------------------------------------------------------------------

class CheckoutService:
    """Orchestrates the checkout pipeline."""

    def __init__(
        self,
        catalog: Catalog,
        coupon_registry: Optional[CouponRegistry] = None,
        tax_calculator: Optional[TaxCalculator] = None,
    ) -> None:
        self._catalog = catalog
        self._coupons = coupon_registry or CouponRegistry()
        self._tax = tax_calculator or TaxCalculator()

    def place_order(
        self,
        cart: Cart,
        customer: Customer,
        coupon_code: Optional[str] = None,
    ) -> Order:
        """Execute the full checkout pipeline and return an immutable Order.

        Steps:
          1. Validate cart is not empty.
          2. Validate stock for every line item.
          3. Resolve coupon (if provided).
          4. Compute discounts and tax.
          5. Reserve stock.
          6. Build and return Order.

        Raises:
            ValueError: cart is empty, stock insufficient, or coupon invalid/expired.
            KeyError:   coupon code not found.
        """
        # 1. Cart must not be empty
        if cart.is_empty:
            raise ValueError("Cannot place an order with an empty cart.")

        # 2. Validate stock
        for line in cart.lines():
            product = self._catalog.get_or_raise(line.sku)
            if product.stock < line.quantity:
                raise ValueError(
                    f"Insufficient stock for {line.sku} ({line.name}): "
                    f"requested {line.quantity}, available {product.stock}"
                )

        # 3. Resolve coupon
        coupon: Optional[Coupon] = None
        if coupon_code:
            coupon = self._coupons.get_or_raise(coupon_code)
            if not coupon.is_valid():
                raise ValueError(f"Coupon {coupon_code!r} is expired.")

        # 4. Compute pricing
        subtotal = cart.subtotal
        discount_breakdown = apply_discounts(
            subtotal=subtotal,
            discount_rate=customer.discount_rate,
            coupon=coupon,
        )
        tax_breakdown = self._tax.breakdown(discount_breakdown["after_coupon"])

        # 5. Reserve stock
        for line in cart.lines():
            self._catalog.reserve(line.sku, line.quantity)

        # 6. Build Order
        order_lines = tuple(
            OrderLine(
                sku=line.sku,
                name=line.name,
                unit_price=line.unit_price,
                quantity=line.quantity,
                line_total=line.line_total,
            )
            for line in cart.lines()
        )

        order = Order(
            order_id=str(uuid.uuid4()),
            customer_id=customer.customer_id,
            customer_type=customer.customer_type.value,
            placed_at=datetime.now(timezone.utc).isoformat(),
            lines=order_lines,
            subtotal=subtotal,
            customer_discount_rate=customer.discount_rate,
            customer_discount_amount=discount_breakdown["customer_discount_amount"],
            after_customer_discount=discount_breakdown["after_customer_discount"],
            coupon_code=coupon.code if coupon else None,
            coupon_discount_amount=discount_breakdown["coupon_discount_amount"],
            after_coupon=discount_breakdown["after_coupon"],
            tax_rate=tax_breakdown["tax_rate"],
            tax_amount=tax_breakdown["tax_amount"],
            grand_total=tax_breakdown["grand_total"],
        )

        cart.clear()
        return order
