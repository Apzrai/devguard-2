"""
refunds.py — Refund processing for LegacyShop.

A refund reverses a completed order, either fully or partially (by line item).

Rules:
  - A full refund returns grand_total to the customer and restocks all items.
  - A partial refund is calculated proportionally:
      refund_amount = grand_total × (refunded_line_total / subtotal)
    This preserves the correct discounted amount — the customer is not refunded
    the pre-discount price.
  - Restocking happens for every refunded line.
  - An order can only be refunded once (tracked by refund registry).
  - You cannot refund more than the order's grand_total.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional
import uuid

from sample_app.catalog import Catalog
from sample_app.checkout import Order, OrderLine


# ---------------------------------------------------------------------------
# Refund data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RefundLine:
    """A single line within a refund."""
    sku: str
    name: str
    quantity_refunded: int
    line_total_refunded: float   # original line total for the refunded units


@dataclass(frozen=True)
class Refund:
    """Immutable refund record."""

    refund_id: str
    order_id: str
    refunded_at: str                # ISO-8601 UTC
    lines: tuple                    # tuple of RefundLine
    refund_type: str                # "FULL" or "PARTIAL"

    # The raw subtotal of the refunded lines (before discount/tax scaling)
    refunded_subtotal: float
    # The proportional share of grand_total being returned
    refund_amount: float


# ---------------------------------------------------------------------------
# RefundService
# ---------------------------------------------------------------------------

class RefundService:
    """Processes refunds against completed orders."""

    def __init__(self, catalog: Catalog) -> None:
        self._catalog = catalog
        # Set of order_ids that have already been refunded
        self._refunded_orders: set[str] = set()

    def refund_full(self, order: Order) -> Refund:
        """Issue a full refund for an entire order.

        Returns the customer grand_total and restocks all items.

        Raises:
            ValueError: if the order has already been refunded.
        """
        self._check_not_already_refunded(order.order_id)

        refund_lines = tuple(
            RefundLine(
                sku=line.sku,
                name=line.name,
                quantity_refunded=line.quantity,
                line_total_refunded=line.line_total,
            )
            for line in order.lines
        )

        # Restock all items
        for line in order.lines:
            self._catalog.restock(line.sku, line.quantity)

        self._refunded_orders.add(order.order_id)

        return Refund(
            refund_id=str(uuid.uuid4()),
            order_id=order.order_id,
            refunded_at=datetime.now(timezone.utc).isoformat(),
            lines=refund_lines,
            refund_type="FULL",
            refunded_subtotal=order.subtotal,
            refund_amount=order.grand_total,
        )

    def refund_partial(
        self,
        order: Order,
        sku_quantities: Dict[str, int],
    ) -> Refund:
        """Issue a partial refund for specific line items and quantities.

        The refund_amount is proportional to the refunded lines' share of the
        original subtotal, applied against grand_total:

            refund_amount = grand_total × (refunded_line_subtotal / subtotal)

        This ensures the customer receives the correctly discounted amount back,
        not the undiscounted unit price.

        Args:
            order:          The original Order record.
            sku_quantities: Dict mapping SKU → number of units to refund.

        Raises:
            ValueError: order already refunded, SKU not in order, quantity exceeds
                        ordered quantity, or subtotal is zero.
        """
        self._check_not_already_refunded(order.order_id)

        # Build a lookup of order lines by SKU
        order_lines_by_sku: Dict[str, OrderLine] = {line.sku: line for line in order.lines}

        refund_lines: List[RefundLine] = []
        refunded_subtotal = 0.0

        for sku, qty in sku_quantities.items():
            if sku not in order_lines_by_sku:
                raise ValueError(f"SKU {sku!r} is not part of order {order.order_id!r}")
            ordered_line = order_lines_by_sku[sku]
            if qty < 1:
                raise ValueError(f"Refund quantity must be >= 1 for SKU {sku!r}, got {qty}")
            if qty > ordered_line.quantity:
                raise ValueError(
                    f"Cannot refund {qty} units of {sku!r}: only {ordered_line.quantity} were ordered"
                )
            per_unit_price = ordered_line.unit_price
            line_total_refunded = round(per_unit_price * qty, 2)
            refund_lines.append(
                RefundLine(
                    sku=sku,
                    name=ordered_line.name,
                    quantity_refunded=qty,
                    line_total_refunded=line_total_refunded,
                )
            )
            refunded_subtotal += line_total_refunded

        refunded_subtotal = round(refunded_subtotal, 2)

        if order.subtotal == 0:
            raise ValueError("Cannot compute proportional refund: original subtotal is zero")

        # Proportional refund: preserve the discount that was applied
        proportion = refunded_subtotal / order.subtotal
        refund_amount = round(order.grand_total * proportion, 2)

        # Restock refunded items
        for rl in refund_lines:
            self._catalog.restock(rl.sku, rl.quantity_refunded)

        self._refunded_orders.add(order.order_id)

        return Refund(
            refund_id=str(uuid.uuid4()),
            order_id=order.order_id,
            refunded_at=datetime.now(timezone.utc).isoformat(),
            lines=tuple(refund_lines),
            refund_type="PARTIAL",
            refunded_subtotal=refunded_subtotal,
            refund_amount=refund_amount,
        )

    def is_refunded(self, order_id: str) -> bool:
        return order_id in self._refunded_orders

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_not_already_refunded(self, order_id: str) -> None:
        if order_id in self._refunded_orders:
            raise ValueError(f"Order {order_id!r} has already been refunded.")
