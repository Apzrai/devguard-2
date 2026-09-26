"""
test_refunds.py — Tests for the refund processing logic.

Business rules under test:
  1. A full refund returns the exact grand_total of the order.
  2. A partial refund is proportional: (refunded_subtotal / original_subtotal) × grand_total.
  3. Refunded items are restocked in the catalog.
  4. An order cannot be refunded twice.
  5. You cannot refund a SKU that was not in the order.
  6. You cannot refund more units than were ordered.
"""

import pytest

from sample_app.catalog import Catalog, Product
from sample_app.cart import Cart
from sample_app.customers import Customer, CustomerType
from sample_app.discount import Coupon, CouponRegistry, CouponType
from sample_app.tax import TaxCalculator
from sample_app.checkout import CheckoutService, Order
from sample_app.refunds import RefundService


# ---------------------------------------------------------------------------
# Fixtures — build real orders to refund against
# ---------------------------------------------------------------------------

@pytest.fixture
def catalog():
    return Catalog([
        Product("SW-001", "DevSuite Pro",  "software", 300.00, 10),
        Product("HW-001", "USB Hub",       "hardware",  60.00, 10),
    ])


@pytest.fixture
def checkout_svc(catalog):
    return CheckoutService(
        catalog=catalog,
        coupon_registry=CouponRegistry({"SAVE10": Coupon("SAVE10", CouponType.FIXED, 10.00)}),
        tax_calculator=TaxCalculator(rate=0.10),
    )


@pytest.fixture
def refund_svc(catalog):
    return RefundService(catalog)


@pytest.fixture
def loyalty_customer():
    return Customer("C-LOY", "Bob Loyal", "bob@x.com", CustomerType.LOYALTY)


@pytest.fixture
def single_item_order(catalog, checkout_svc, loyalty_customer):
    """Order: 1 × SW-001 ($300), loyalty 10% → $270, tax 10% → grand_total $297."""
    cart = Cart(catalog)
    cart.add("SW-001", 1)
    return checkout_svc.place_order(cart, loyalty_customer)


@pytest.fixture
def multi_item_order(catalog, checkout_svc, loyalty_customer):
    """Order: 2 × SW-001 ($600) + 1 × HW-001 ($60) = $660 subtotal,
    loyalty 10% → $594, tax 10% → grand_total $653.40."""
    cart = Cart(catalog)
    cart.add("SW-001", 2)
    cart.add("HW-001", 1)
    return checkout_svc.place_order(cart, loyalty_customer)


@pytest.fixture
def order_with_coupon(catalog, checkout_svc, loyalty_customer):
    """Order: 1 × SW-001 ($300), 10% loyalty → $270, $10 coupon → $260, 10% tax → $286."""
    cart = Cart(catalog)
    cart.add("SW-001", 1)
    return checkout_svc.place_order(cart, loyalty_customer, coupon_code="SAVE10")


# ---------------------------------------------------------------------------
# Full refund
# ---------------------------------------------------------------------------

class TestFullRefund:
    def test_full_refund_amount_equals_grand_total(
        self, single_item_order, refund_svc
    ):
        refund = refund_svc.refund_full(single_item_order)
        assert refund.refund_amount == pytest.approx(single_item_order.grand_total)

    def test_full_refund_type_is_full(self, single_item_order, refund_svc):
        refund = refund_svc.refund_full(single_item_order)
        assert refund.refund_type == "FULL"

    def test_full_refund_restocks_items(self, single_item_order, refund_svc, catalog):
        stock_before = catalog.get("SW-001").stock
        refund_svc.refund_full(single_item_order)
        assert catalog.get("SW-001").stock == stock_before + 1

    def test_full_refund_includes_all_lines(self, multi_item_order, refund_svc):
        refund = refund_svc.refund_full(multi_item_order)
        refunded_skus = {rl.sku for rl in refund.lines}
        assert "SW-001" in refunded_skus
        assert "HW-001" in refunded_skus

    def test_full_refund_returns_grand_total_with_coupon(
        self, order_with_coupon, refund_svc
    ):
        refund = refund_svc.refund_full(order_with_coupon)
        assert refund.refund_amount == pytest.approx(order_with_coupon.grand_total)

    def test_double_refund_raises(self, single_item_order, refund_svc):
        refund_svc.refund_full(single_item_order)
        with pytest.raises(ValueError, match="already been refunded"):
            refund_svc.refund_full(single_item_order)


# ---------------------------------------------------------------------------
# Partial refund
# ---------------------------------------------------------------------------

class TestPartialRefund:
    def test_partial_refund_type_is_partial(self, multi_item_order, refund_svc):
        refund = refund_svc.refund_partial(multi_item_order, {"HW-001": 1})
        assert refund.refund_type == "PARTIAL"

    def test_partial_refund_proportional_amount(self, multi_item_order, refund_svc):
        """
        Multi-item order: subtotal=$660, grand_total=$653.40
        Refunding HW-001 ($60): proportion = 60/660 = 0.0909...
        refund_amount = 653.40 × (60/660) = 59.40
        """
        refund = refund_svc.refund_partial(multi_item_order, {"HW-001": 1})
        expected = round(multi_item_order.grand_total * (60.00 / 660.00), 2)
        assert refund.refund_amount == pytest.approx(expected, abs=0.01)

    def test_partial_refund_restocks_only_refunded_sku(
        self, multi_item_order, refund_svc, catalog
    ):
        hw_stock_before = catalog.get("HW-001").stock
        sw_stock_before = catalog.get("SW-001").stock
        refund_svc.refund_partial(multi_item_order, {"HW-001": 1})
        assert catalog.get("HW-001").stock == hw_stock_before + 1
        assert catalog.get("SW-001").stock == sw_stock_before  # unchanged

    def test_partial_refund_refunds_discounted_amount_not_full_price(
        self, multi_item_order, refund_svc
    ):
        """
        Verify the refund is less than the undiscounted price,
        because it's proportional to grand_total (which includes discount + tax).

        HW-001 unit price = $60.00 (undiscounted).
        grand_total = $653.40 on $660.00 subtotal.
        Effective price per dollar of subtotal = 653.40/660 = 0.9900
        Refund for $60 of subtotal = 60 × 0.9900 = $59.40
        This is less than $60 × (1+tax) = $66.00, confirming discount is preserved.
        """
        refund = refund_svc.refund_partial(multi_item_order, {"HW-001": 1})
        undiscounted_with_tax = round(60.00 * 1.10, 2)   # $66.00
        assert refund.refund_amount < undiscounted_with_tax
        assert refund.refund_amount == pytest.approx(59.40, abs=0.01)

    def test_partial_refund_partial_quantity(self, multi_item_order, refund_svc):
        """Refund 1 of the 2 SW-001 items."""
        refund = refund_svc.refund_partial(multi_item_order, {"SW-001": 1})
        # 1 unit of SW-001 = $300 of $660 subtotal
        expected = round(multi_item_order.grand_total * (300.00 / 660.00), 2)
        assert refund.refund_amount == pytest.approx(expected, abs=0.01)

    def test_partial_refund_sku_not_in_order_raises(
        self, single_item_order, refund_svc
    ):
        with pytest.raises(ValueError, match="not part of order"):
            refund_svc.refund_partial(single_item_order, {"HW-001": 1})

    def test_partial_refund_quantity_exceeds_ordered_raises(
        self, single_item_order, refund_svc
    ):
        with pytest.raises(ValueError, match="Cannot refund"):
            refund_svc.refund_partial(single_item_order, {"SW-001": 99})

    def test_partial_refund_zero_quantity_raises(self, single_item_order, refund_svc):
        with pytest.raises(ValueError, match="Refund quantity"):
            refund_svc.refund_partial(single_item_order, {"SW-001": 0})

    def test_double_partial_refund_raises(self, multi_item_order, refund_svc):
        refund_svc.refund_partial(multi_item_order, {"HW-001": 1})
        with pytest.raises(ValueError, match="already been refunded"):
            refund_svc.refund_partial(multi_item_order, {"SW-001": 1})


# ---------------------------------------------------------------------------
# is_refunded()
# ---------------------------------------------------------------------------

class TestRefundStatus:
    def test_order_not_refunded_initially(self, single_item_order, refund_svc):
        assert not refund_svc.is_refunded(single_item_order.order_id)

    def test_order_marked_refunded_after_full_refund(
        self, single_item_order, refund_svc
    ):
        refund_svc.refund_full(single_item_order)
        assert refund_svc.is_refunded(single_item_order.order_id)

    def test_order_marked_refunded_after_partial_refund(
        self, multi_item_order, refund_svc
    ):
        refund_svc.refund_partial(multi_item_order, {"HW-001": 1})
        assert refund_svc.is_refunded(multi_item_order.order_id)
