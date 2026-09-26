"""
test_checkout.py — Tests for the checkout pipeline and pricing chain.

Business rules under test:
  1. Customer discount applied first to raw subtotal.
  2. Coupon applied second, to post-customer-discount amount.
  3. Tax applied last, to post-coupon amount.
  4. Grand total = taxable_amount + tax.
  5. Stock is reserved after successful checkout.
  6. Cart is cleared after successful checkout.
  7. Empty cart is rejected.
  8. Insufficient stock is rejected.
  9. Expired coupon is rejected.
"""

import pytest
from datetime import date

from sample_app.catalog import Catalog, Product
from sample_app.cart import Cart
from sample_app.customers import Customer, CustomerType
from sample_app.discount import Coupon, CouponRegistry, CouponType
from sample_app.tax import TaxCalculator
from sample_app.checkout import CheckoutService


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def catalog():
    return Catalog([
        Product("SW-001", "DevSuite Pro",    "software", 300.00, 10),
        Product("HW-001", "USB Hub",         "hardware",  60.00,  3),
        Product("SV-001", "Support 1yr",     "services", 200.00, 50),
    ])


@pytest.fixture
def cart(catalog):
    return Cart(catalog)


@pytest.fixture
def new_customer():
    return Customer("C-NEW", "Alice New", "alice@x.com", CustomerType.NEW)


@pytest.fixture
def loyalty_customer():
    return Customer("C-LOY", "Bob Loyal", "bob@x.com", CustomerType.LOYALTY)


@pytest.fixture
def enterprise_customer():
    return Customer("C-ENT", "Acme Corp", "acme@x.com", CustomerType.ENTERPRISE)


@pytest.fixture
def coupon_registry():
    return CouponRegistry({
        "SAVE10":   Coupon("SAVE10",   CouponType.FIXED,      10.00),
        "PCTOFF15": Coupon("PCTOFF15", CouponType.PERCENTAGE,  0.15),
        "EXPIRED":  Coupon("EXPIRED",  CouponType.FIXED,       5.00, expires_on=date(2000, 1, 1)),
    })


@pytest.fixture
def checkout(catalog, coupon_registry):
    return CheckoutService(
        catalog=catalog,
        coupon_registry=coupon_registry,
        tax_calculator=TaxCalculator(rate=0.10),  # 10% for clean math
    )


# ---------------------------------------------------------------------------
# Basic checkout
# ---------------------------------------------------------------------------

class TestCheckoutBasic:
    def test_successful_order_has_order_id(self, cart, new_customer, checkout):
        cart.add("SW-001", 1)
        order = checkout.place_order(cart, new_customer)
        assert order.order_id is not None
        assert len(order.order_id) > 0

    def test_order_stores_customer_id(self, cart, loyalty_customer, checkout):
        cart.add("SW-001", 1)
        order = checkout.place_order(cart, loyalty_customer)
        assert order.customer_id == "C-LOY"

    def test_cart_cleared_after_checkout(self, cart, new_customer, checkout):
        cart.add("SW-001", 1)
        checkout.place_order(cart, new_customer)
        assert cart.is_empty

    def test_empty_cart_raises(self, cart, new_customer, checkout):
        with pytest.raises(ValueError, match="empty"):
            checkout.place_order(cart, new_customer)


# ---------------------------------------------------------------------------
# Pricing chain — the critical business rule tests
# ---------------------------------------------------------------------------

class TestCheckoutPricingChain:
    def test_new_customer_5pct_discount(self, cart, new_customer, checkout):
        """
        $300.00 subtotal
        - 5% customer discount → $285.00
        - no coupon
        - 10% tax on $285.00 = $28.50
        - grand total = $313.50
        """
        cart.add("SW-001", 1)
        order = checkout.place_order(cart, new_customer)
        assert order.subtotal == 300.00
        assert order.customer_discount_rate == 0.05
        assert order.after_customer_discount == 285.00
        assert order.after_coupon == 285.00
        assert order.tax_amount == pytest.approx(28.50)
        assert order.grand_total == pytest.approx(313.50)

    def test_loyalty_customer_10pct_discount(self, cart, loyalty_customer, checkout):
        """
        $300.00 subtotal
        - 10% customer discount → $270.00
        - no coupon
        - 10% tax on $270.00 = $27.00
        - grand total = $297.00
        """
        cart.add("SW-001", 1)
        order = checkout.place_order(cart, loyalty_customer)
        assert order.customer_discount_rate == 0.10
        assert order.after_customer_discount == 270.00
        assert order.grand_total == pytest.approx(297.00)

    def test_enterprise_customer_10pct_discount(self, cart, enterprise_customer, checkout):
        """
        $300.00 subtotal
        - 10% enterprise discount → $270.00
        - 10% tax on $270.00 = $27.00
        - grand total = $297.00
        """
        cart.add("SW-001", 1)
        order = checkout.place_order(cart, enterprise_customer)
        assert order.customer_discount_rate == 0.10
        assert order.after_customer_discount == 270.00
        assert order.grand_total == pytest.approx(297.00)

    def test_coupon_applied_after_customer_discount(
        self, cart, loyalty_customer, checkout
    ):
        """
        Business rule: coupon applies to post-customer-discount amount.

        $300.00 subtotal
        - 10% loyalty discount → $270.00
        - $10 fixed coupon on $270.00 → $260.00  (taxable base)
        - 10% tax on $260.00 = $26.00
        - grand total = $286.00
        """
        cart.add("SW-001", 1)
        order = checkout.place_order(cart, loyalty_customer, coupon_code="SAVE10")
        assert order.after_customer_discount == 270.00
        assert order.coupon_discount_amount == 10.00
        assert order.after_coupon == 260.00
        assert order.tax_amount == pytest.approx(26.00)
        assert order.grand_total == pytest.approx(286.00)

    def test_tax_computed_on_post_coupon_amount(self, cart, new_customer, checkout):
        """
        $300.00 subtotal
        - 5% new customer discount → $285.00
        - 15% coupon on $285.00 → $242.25  (taxable base)
        - 10% tax on $242.25 = $24.225 → $24.23
        - grand total = $266.48
        """
        cart.add("SW-001", 1)
        order = checkout.place_order(cart, new_customer, coupon_code="PCTOFF15")
        assert order.after_customer_discount == 285.00
        assert order.after_coupon == pytest.approx(242.25)
        assert order.tax_amount == pytest.approx(24.23, abs=0.01)
        assert order.grand_total == pytest.approx(266.48, abs=0.01)

    def test_multi_item_subtotal(self, cart, loyalty_customer, checkout):
        """
        2 × SW-001 ($300 each) + 1 × HW-001 ($60) = $660 subtotal
        - 10% discount → $594.00
        - 10% tax = $59.40
        - grand total = $653.40
        """
        cart.add("SW-001", 2)
        cart.add("HW-001", 1)
        order = checkout.place_order(cart, loyalty_customer)
        assert order.subtotal == 660.00
        assert order.after_customer_discount == 594.00
        assert order.grand_total == pytest.approx(653.40)


# ---------------------------------------------------------------------------
# Stock validation
# ---------------------------------------------------------------------------

class TestCheckoutStock:
    def test_stock_reserved_after_checkout(self, cart, new_customer, checkout, catalog):
        cart.add("HW-001", 2)
        initial_stock = catalog.get("HW-001").stock
        checkout.place_order(cart, new_customer)
        assert catalog.get("HW-001").stock == initial_stock - 2

    def test_insufficient_stock_raises(self, cart, new_customer, checkout):
        cart.add("HW-001", 100)
        with pytest.raises(ValueError, match="Insufficient stock"):
            checkout.place_order(cart, new_customer)


# ---------------------------------------------------------------------------
# Coupon edge cases
# ---------------------------------------------------------------------------

class TestCheckoutCoupons:
    def test_expired_coupon_raises(self, cart, new_customer, checkout):
        cart.add("SW-001", 1)
        with pytest.raises(ValueError, match="expired"):
            checkout.place_order(cart, new_customer, coupon_code="EXPIRED")

    def test_unknown_coupon_raises(self, cart, new_customer, checkout):
        cart.add("SW-001", 1)
        with pytest.raises(KeyError):
            checkout.place_order(cart, new_customer, coupon_code="FAKECODE")

    def test_order_without_coupon_has_none_coupon_code(self, cart, new_customer, checkout):
        cart.add("SW-001", 1)
        order = checkout.place_order(cart, new_customer)
        assert order.coupon_code is None
        assert order.coupon_discount_amount == 0.00
