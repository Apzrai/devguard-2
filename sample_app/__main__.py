"""
__main__.py — LegacyShop demo runner.

Runs a complete end-to-end scenario:
  1. Browse the catalog
  2. Build a cart for three customer types
  3. Check out each cart (with and without coupon)
  4. Issue a full and partial refund

Run with:  python -m sample_app
"""

from sample_app.catalog import Catalog
from sample_app.cart import Cart
from sample_app.customers import Customer, CustomerType
from sample_app.discount import CouponRegistry
from sample_app.tax import TaxCalculator
from sample_app.checkout import CheckoutService
from sample_app.refunds import RefundService


SEP = "-" * 60


def fmt_order(order) -> str:
    lines = [
        f"  Order ID      : {order.order_id}",
        f"  Customer      : {order.customer_id} ({order.customer_type})",
        f"  Subtotal      : ${order.subtotal:.2f}",
        f"  Cust. discount: -{order.customer_discount_rate*100:.0f}%  "
        f"(-${order.customer_discount_amount:.2f})  -> ${order.after_customer_discount:.2f}",
    ]
    if order.coupon_code:
        lines.append(
            f"  Coupon {order.coupon_code:<8}: -${order.coupon_discount_amount:.2f}"
            f"  -> ${order.after_coupon:.2f}"
        )
    lines += [
        f"  Tax ({order.tax_rate*100:.1f}%)    : +${order.tax_amount:.2f}",
        f"  Grand Total   : ${order.grand_total:.2f}",
    ]
    return "\n".join(lines)


def main() -> None:
    print(SEP)
    print("  LegacyShop Demo")
    print(SEP)

    catalog = Catalog()
    coupon_registry = CouponRegistry()
    tax = TaxCalculator()
    checkout = CheckoutService(catalog, coupon_registry, tax)
    refund_svc = RefundService(catalog)

    # ----------------------------------------------------------------
    # 1. Catalog overview
    # ----------------------------------------------------------------
    print("\n[1] Product Catalog")
    for p in catalog.all():
        print(f"  {p.sku:<8} {p.name:<25} ${p.unit_price:.2f}  (stock: {p.stock})")

    # ----------------------------------------------------------------
    # 2. New customer - no coupon
    # ----------------------------------------------------------------
    print(f"\n{SEP}")
    print("[2] New customer checkout - no coupon")
    new_cust = Customer("C-001", "Alice New", "alice@shop.com", CustomerType.NEW)
    cart = Cart(catalog)
    cart.add("SW-001", 1)
    cart.add("HW-001", 1)
    order_new = checkout.place_order(cart, new_cust)
    print(fmt_order(order_new))

    # ----------------------------------------------------------------
    # 3. Loyalty customer - with fixed coupon
    # ----------------------------------------------------------------
    print(f"\n{SEP}")
    print("[3] Loyalty customer checkout - SAVE10 coupon")
    loyalty_cust = Customer("C-002", "Bob Loyal", "bob@shop.com", CustomerType.LOYALTY)
    cart = Cart(catalog)
    cart.add("SW-001", 1)
    cart.add("SV-001", 1)
    order_loyalty = checkout.place_order(cart, loyalty_cust, coupon_code="SAVE10")
    print(fmt_order(order_loyalty))

    # ----------------------------------------------------------------
    # 4. Enterprise customer - with percentage coupon
    # ----------------------------------------------------------------
    print(f"\n{SEP}")
    print("[4] Enterprise customer checkout - SUMMER15 coupon")
    ent_cust = Customer("C-003", "Acme Corp", "acme@shop.com", CustomerType.ENTERPRISE)
    cart = Cart(catalog)
    cart.add("SW-001", 2)
    cart.add("SV-002", 1)
    order_ent = checkout.place_order(cart, ent_cust, coupon_code="SUMMER15")
    print(fmt_order(order_ent))

    # ----------------------------------------------------------------
    # 5. Full refund
    # ----------------------------------------------------------------
    print(f"\n{SEP}")
    print("[5] Full refund - New customer order")
    refund_full = refund_svc.refund_full(order_new)
    print(f"  Refund ID   : {refund_full.refund_id}")
    print(f"  Type        : {refund_full.refund_type}")
    print(f"  Amount      : ${refund_full.refund_amount:.2f}")

    # ----------------------------------------------------------------
    # 6. Partial refund
    # ----------------------------------------------------------------
    print(f"\n{SEP}")
    print("[6] Partial refund - Enterprise order (1 x SW-001)")
    refund_partial = refund_svc.refund_partial(order_ent, {"SW-001": 1})
    print(f"  Refund ID   : {refund_partial.refund_id}")
    print(f"  Type        : {refund_partial.refund_type}")
    print(f"  Refunded    : ${refund_partial.refunded_subtotal:.2f} of "
          f"${order_ent.subtotal:.2f} subtotal")
    print(f"  Amount      : ${refund_partial.refund_amount:.2f}")

    print(f"\n{SEP}")
    print("  Demo complete.")
    print(SEP)


if __name__ == "__main__":
    main()
