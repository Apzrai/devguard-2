"""
test_catalog.py — Tests for the product catalog.
"""

import pytest
from sample_app.catalog import Catalog, Product


@pytest.fixture
def catalog():
    """Fresh catalog with default products."""
    return Catalog()


@pytest.fixture
def small_catalog():
    """Minimal catalog with predictable data."""
    return Catalog([
        Product("A-001", "Alpha Widget",  "widgets", 10.00, 5),
        Product("A-002", "Beta Gadget",   "gadgets", 20.00, 0),
        Product("A-003", "Gamma Widget",  "widgets", 30.00, 3),
    ])


class TestProductModel:
    def test_valid_product_created(self):
        p = Product("T-001", "Test Item", "test", 9.99, 10)
        assert p.sku == "T-001"
        assert p.unit_price == 9.99
        assert p.stock == 10

    def test_negative_price_rejected(self):
        with pytest.raises(ValueError, match="unit_price"):
            Product("T-001", "Bad", "test", -1.00, 10)

    def test_negative_stock_rejected(self):
        with pytest.raises(ValueError, match="stock"):
            Product("T-001", "Bad", "test", 10.00, -1)


class TestCatalogLookup:
    def test_get_existing_sku(self, small_catalog):
        p = small_catalog.get("A-001")
        assert p is not None
        assert p.name == "Alpha Widget"

    def test_get_missing_sku_returns_none(self, small_catalog):
        assert small_catalog.get("MISSING") is None

    def test_get_or_raise_missing_raises(self, small_catalog):
        with pytest.raises(KeyError, match="MISSING"):
            small_catalog.get_or_raise("MISSING")

    def test_all_returns_all_products(self, small_catalog):
        assert len(small_catalog.all()) == 3


class TestCatalogSearch:
    def test_by_category_filters_correctly(self, small_catalog):
        widgets = small_catalog.by_category("widgets")
        skus = {p.sku for p in widgets}
        assert skus == {"A-001", "A-003"}

    def test_by_category_case_insensitive(self, small_catalog):
        assert len(small_catalog.by_category("WIDGETS")) == 2

    def test_search_by_name_substring(self, small_catalog):
        results = small_catalog.search("widget")
        assert len(results) == 2

    def test_search_by_sku_substring(self, small_catalog):
        results = small_catalog.search("A-002")
        assert len(results) == 1
        assert results[0].sku == "A-002"

    def test_in_stock_excludes_zero_stock(self, small_catalog):
        in_stock = small_catalog.in_stock()
        skus = {p.sku for p in in_stock}
        assert "A-002" not in skus
        assert "A-001" in skus


class TestCatalogInventory:
    def test_reserve_reduces_stock(self, small_catalog):
        small_catalog.reserve("A-001", 2)
        assert small_catalog.get("A-001").stock == 3

    def test_reserve_insufficient_stock_raises(self, small_catalog):
        with pytest.raises(ValueError, match="Insufficient stock"):
            small_catalog.reserve("A-001", 10)

    def test_restock_increases_stock(self, small_catalog):
        small_catalog.restock("A-001", 5)
        assert small_catalog.get("A-001").stock == 10

    def test_restock_negative_quantity_raises(self, small_catalog):
        with pytest.raises(ValueError):
            small_catalog.restock("A-001", -1)
