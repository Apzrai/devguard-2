"""
catalog.py — Product catalog for LegacyShop.

Provides an in-memory product registry with search and filtering.
Each product has an SKU, name, category, unit price, and stock quantity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Product:
    """A single product available for purchase."""

    sku: str
    name: str
    category: str
    unit_price: float  # base price in USD, before any discounts or tax
    stock: int

    def __post_init__(self) -> None:
        if self.unit_price < 0:
            raise ValueError(f"unit_price must be >= 0, got {self.unit_price}")
        if self.stock < 0:
            raise ValueError(f"stock must be >= 0, got {self.stock}")


# ---------------------------------------------------------------------------
# Default product catalogue
# ---------------------------------------------------------------------------

_DEFAULT_PRODUCTS: List[Product] = [
    # Software
    Product("SW-001", "DevSuite Pro",        "software",  299.00, 999),
    Product("SW-002", "DataVault Standard",  "software",  149.00, 999),
    Product("SW-003", "CloudSync Basic",     "software",   49.00, 999),
    # Hardware
    Product("HW-001", "Wireless Keyboard",   "hardware",   79.00,  50),
    Product("HW-002", "USB-C Hub 7-port",    "hardware",   59.00,  30),
    Product("HW-003", "Ergonomic Mouse",     "hardware",   45.00,  75),
    # Services
    Product("SV-001", "Priority Support 1yr","services",  199.00, 999),
    Product("SV-002", "Setup & Config",      "services",   99.00, 999),
    Product("SV-003", "Training Session",    "services",  249.00, 999),
]


class Catalog:
    """In-memory product catalog."""

    def __init__(self, products: Optional[List[Product]] = None) -> None:
        self._products: dict[str, Product] = {}
        for p in (products or _DEFAULT_PRODUCTS):
            self._products[p.sku] = p

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, sku: str) -> Optional[Product]:
        """Return the product with the given SKU, or None."""
        return self._products.get(sku)

    def get_or_raise(self, sku: str) -> Product:
        """Return the product or raise KeyError."""
        product = self._products.get(sku)
        if product is None:
            raise KeyError(f"Product not found: {sku}")
        return product

    # ------------------------------------------------------------------
    # Search and filter
    # ------------------------------------------------------------------

    def all(self) -> List[Product]:
        """Return all products."""
        return list(self._products.values())

    def by_category(self, category: str) -> List[Product]:
        """Return all products in a given category (case-insensitive)."""
        cat = category.lower()
        return [p for p in self._products.values() if p.category.lower() == cat]

    def search(self, query: str) -> List[Product]:
        """Return products whose name or SKU contains the query string (case-insensitive)."""
        q = query.lower()
        return [
            p for p in self._products.values()
            if q in p.name.lower() or q in p.sku.lower()
        ]

    def in_stock(self) -> List[Product]:
        """Return only products with stock > 0."""
        return [p for p in self._products.values() if p.stock > 0]

    # ------------------------------------------------------------------
    # Inventory management (used by checkout)
    # ------------------------------------------------------------------

    def reserve(self, sku: str, quantity: int) -> None:
        """Decrement stock for an SKU. Raises ValueError if insufficient stock."""
        product = self.get_or_raise(sku)
        if product.stock < quantity:
            raise ValueError(
                f"Insufficient stock for {sku}: requested {quantity}, available {product.stock}"
            )
        product.stock -= quantity

    def restock(self, sku: str, quantity: int) -> None:
        """Return stock to catalog (used by refund flow)."""
        product = self.get_or_raise(sku)
        if quantity < 0:
            raise ValueError("restock quantity must be >= 0")
        product.stock += quantity
