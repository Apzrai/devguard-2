# LegacyShop — Business Rules

This document is the authoritative reference for LegacyShop's pricing and
operational rules.  Any change to the application that contradicts a rule
listed here is a regression and must be detected by the test suite.

---

## 1. Customer Types

LegacyShop recognises three customer types.  Each type has a defined discount rate.

| Type | Description | Discount Rate |
|---|---|---|
| `NEW` | First-time or unverified customers | **5%** |
| `LOYALTY` | Returning customers enrolled in the loyalty programme | **10%** |
| `ENTERPRISE` | Business accounts on a negotiated contract | **10%** (global default) |

Enterprise customers may have a per-account `contract_discount_rate` that overrides
the global `ENTERPRISE_DISCOUNT` constant.  Only Enterprise customers may have a
contract rate; Loyalty and New customers may not.

### Invariant: Discount rates are independent

`NEW_CUSTOMER_DISCOUNT`, `LOYALTY_DISCOUNT`, and `ENTERPRISE_DISCOUNT` are separate
constants.  A change to one constant must not affect the others.

**Example of a violation:** Updating `ENTERPRISE_DISCOUNT` from `0.10` to `0.15`
accidentally also sets `LOYALTY_DISCOUNT` to `0.15`.  This is the controlled failure
scenario used in DEVGUARD testing.

---

## 2. Pricing Pipeline

All pricing calculations follow a strict order.  Steps must not be reordered.

```
Raw subtotal
    │
    ▼
Step 1: Customer discount applied to raw subtotal
    │
    ▼
Step 2: Coupon discount applied to post-customer-discount amount
    │
    ▼
Step 3: Tax calculated on post-coupon amount  ← this is the taxable base
    │
    ▼
Grand Total = taxable base + tax
```

### 2.1 Customer Discount

- Applied first, directly to the raw cart subtotal.
- Formula: `after_customer_discount = subtotal × (1 − discount_rate)`

### 2.2 Coupon Discount

- Applied second, to the result of Step 1 (not to the original subtotal).
- Two coupon types are supported:
  - **FIXED** — reduces the running total by a flat dollar amount.
  - **PERCENTAGE** — reduces the running total by a percentage fraction.
- A coupon cannot reduce the payable amount below `$0.00`.
- An expired coupon (past its `expires_on` date) is rejected at checkout.
- If no coupon is provided, this step is a no-op.

### 2.3 Tax

- Calculated last, on the amount remaining after both discounts.
- Default tax rate: **8.5%**.
- Formula: `tax_amount = taxable_base × tax_rate`
- `grand_total = taxable_base + tax_amount`
- Tax is rounded to 2 decimal places.

---

## 3. Order Rules

- An order cannot be placed on an empty cart.
- An order cannot be placed if any line item has insufficient stock.
- When an order is placed, stock is reserved (decremented) for every line item.
- The cart is cleared after a successful order.
- Orders are immutable after placement (frozen dataclass).

---

## 4. Refund Rules

- **Full refund:** returns `grand_total` to the customer; restocks all items.
- **Partial refund:** returns a proportional amount:

  ```
  refund_amount = grand_total × (refunded_line_subtotal / original_subtotal)
  ```

  This ensures the refunded amount reflects the discounted price, not the
  original undiscounted unit price.

- Items are restocked when a refund is issued.
- An order can only be refunded once (full or partial).
- You cannot refund a SKU that was not part of the original order.
- You cannot refund more units than were originally ordered.

---

## 5. Catalog Rules

- Every product has a unique SKU.
- Unit prices and stock quantities must be non-negative.
- Adding the same SKU to the cart twice increments the quantity; it does not
  create a duplicate line.
- Cart line quantities must be positive integers (≥ 1).

---

## 6. Coupon Rules

| Rule | Detail |
|---|---|
| Fixed coupon | `value` is a dollar amount, e.g. `10.00` means $10 off |
| Percentage coupon | `value` is a fraction in [0.0, 1.0], e.g. `0.15` means 15% off |
| Expiry | Coupons are valid on their `expires_on` date; invalid the day after |
| Floor | Result after coupon is floored at $0.00 |
| Case | Coupon codes are case-insensitive at lookup |

---

## 7. Controlled Failure Scenario (for DEVGUARD testing)

**Maintenance request:**
> "Update the Enterprise discount rate from 10% to 15% to match the new pricing policy."

**Correct change:** `ENTERPRISE_DISCOUNT = 0.15`

**Accidental incorrect change:** Also sets `LOYALTY_DISCOUNT = 0.15`

**Detection:** The following tests will fail if Loyalty is accidentally changed:
- `test_loyalty_discount_is_10_percent` — constant value check
- `test_loyalty_customer_rate` — function return value check
- `test_loyalty_customer_100_dollar_order_discount` — math check ($100 → $90.00)
- `test_loyalty_customer_10pct_discount` — checkout integration check
- `test_discount_rates_are_independent` — independence assertion

These failures are caught by DEVGUARD's behavioral verification step before any
change is merged.
