"""
cart.py — Shopping cart for LegacyShop.

A Cart holds line items keyed by SKU.  It computes the raw subtotal (sum of
unit prices × quantities) without any discounts or tax — those are applied
downstream by discount.py and tax.py.

Invariants:
  - Line item quantities must be positive integers.
  - A SKU can only appear once in the cart (adding the same SKU increases quantity).
  - The subtotal is always the sum of (unit_price × quantity) for each line.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from sample_app.catalog import Catalog, Product


@dataclass
class CartLine:
    """A single line in the shopping cart."""

    sku: str
    name: str
    unit_price: float
    quantity: int

    @property
    def line_total(self) -> float:
        return round(self.unit_price * self.quantity, 2)


class Cart:
    """A shopping cart for a single customer session."""

    def __init__(self, catalog: Catalog) -> None:
        self._catalog = catalog
        self._lines: Dict[str, CartLine] = {}

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add(self, sku: str, quantity: int = 1) -> CartLine:
        """Add `quantity` units of `sku` to the cart.

        If the SKU is already in the cart, the quantity is incremented.
        Raises:
            KeyError:   if the SKU is not found in the catalog.
            ValueError: if quantity < 1.
        """
        if quantity < 1:
            raise ValueError(f"quantity must be >= 1, got {quantity}")
        product: Product = self._catalog.get_or_raise(sku)

        if sku in self._lines:
            self._lines[sku].quantity += quantity
        else:
            self._lines[sku] = CartLine(
                sku=sku,
                name=product.name,
                unit_price=product.unit_price,
                quantity=quantity,
            )
        return self._lines[sku]

    def remove(self, sku: str, quantity: int = 1) -> Optional[CartLine]:
        """Remove `quantity` units of `sku` from the cart.

        If reducing quantity to 0 or below, the line is removed entirely.
        Returns the updated (or removed) CartLine, or None if the SKU was not present.
        Raises:
            ValueError: if quantity < 1.
        """
        if quantity < 1:
            raise ValueError(f"quantity must be >= 1, got {quantity}")
        if sku not in self._lines:
            return None
        line = self._lines[sku]
        line.quantity -= quantity
        if line.quantity <= 0:
            del self._lines[sku]
            return None
        return line

    def clear(self) -> None:
        """Remove all items from the cart."""
        self._lines.clear()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def lines(self) -> List[CartLine]:
        """Return all cart lines."""
        return list(self._lines.values())

    def get_line(self, sku: str) -> Optional[CartLine]:
        return self._lines.get(sku)

    @property
    def subtotal(self) -> float:
        """Raw subtotal: sum of (unit_price × quantity) for all lines, before discounts or tax."""
        return round(sum(line.line_total for line in self._lines.values()), 2)

    @property
    def item_count(self) -> int:
        """Total number of individual units across all lines."""
        return sum(line.quantity for line in self._lines.values())

    @property
    def is_empty(self) -> bool:
        return len(self._lines) == 0
