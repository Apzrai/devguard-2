"""
test_cart.py — Tests for shopping cart logic.
"""

import pytest
from sample_app.catalog import Catalog, Product
from sample_app.cart import Cart


@pytest.fixture
def catalog():
    return Catalog([
        Product("P-001", "Widget A", "widgets", 10.00, 20),
        Product("P-002", "Widget B", "widgets", 25.00, 5),
        Product("P-003", "Gadget C", "gadgets", 50.00, 2),
    ])


@pytest.fixture
def cart(catalog):
    return Cart(catalog)


class TestCartAdd:
    def test_add_single_item(self, cart):
        line = cart.add("P-001")
        assert line.quantity == 1
        assert line.unit_price == 10.00

    def test_add_multiple_quantity(self, cart):
        line = cart.add("P-001", 3)
        assert line.quantity == 3

    def test_add_same_sku_twice_increments_quantity(self, cart):
        cart.add("P-001", 2)
        line = cart.add("P-001", 3)
        assert line.quantity == 5

    def test_add_unknown_sku_raises(self, cart):
        with pytest.raises(KeyError):
            cart.add("MISSING")

    def test_add_zero_quantity_raises(self, cart):
        with pytest.raises(ValueError, match="quantity"):
            cart.add("P-001", 0)

    def test_add_negative_quantity_raises(self, cart):
        with pytest.raises(ValueError, match="quantity"):
            cart.add("P-001", -1)


class TestCartRemove:
    def test_remove_reduces_quantity(self, cart):
        cart.add("P-001", 5)
        cart.remove("P-001", 2)
        assert cart.get_line("P-001").quantity == 3

    def test_remove_all_removes_line(self, cart):
        cart.add("P-001", 3)
        result = cart.remove("P-001", 3)
        assert result is None
        assert cart.get_line("P-001") is None

    def test_remove_more_than_present_removes_line(self, cart):
        cart.add("P-001", 2)
        result = cart.remove("P-001", 10)
        assert result is None

    def test_remove_from_empty_cart_returns_none(self, cart):
        assert cart.remove("P-001") is None

    def test_remove_zero_quantity_raises(self, cart):
        cart.add("P-001", 1)
        with pytest.raises(ValueError):
            cart.remove("P-001", 0)


class TestCartSubtotal:
    def test_subtotal_single_item(self, cart):
        cart.add("P-001", 1)
        assert cart.subtotal == 10.00

    def test_subtotal_multiple_items(self, cart):
        cart.add("P-001", 2)   # 20.00
        cart.add("P-002", 1)   # 25.00
        assert cart.subtotal == 45.00

    def test_subtotal_empty_cart_is_zero(self, cart):
        assert cart.subtotal == 0.00

    def test_item_count(self, cart):
        cart.add("P-001", 3)
        cart.add("P-002", 2)
        assert cart.item_count == 5

    def test_is_empty_true_for_new_cart(self, cart):
        assert cart.is_empty

    def test_is_empty_false_after_add(self, cart):
        cart.add("P-001")
        assert not cart.is_empty

    def test_clear_empties_cart(self, cart):
        cart.add("P-001", 5)
        cart.clear()
        assert cart.is_empty
        assert cart.subtotal == 0.00

    def test_line_total_is_unit_price_times_quantity(self, cart):
        cart.add("P-002", 3)
        line = cart.get_line("P-002")
        assert line.line_total == 75.00
