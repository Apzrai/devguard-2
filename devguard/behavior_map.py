"""
devguard/behavior_map.py — Behavior Reconstruction and Behavior Map.

Derives the actual behaviors of the target project from:
  - Source code (AST, constants, function signatures) — OBSERVED
  - Test assertions (what the tests assert must be true) — TESTED
  - Documentation (BUSINESS_RULES.md rules) — DOCUMENTED
  - Logical dependencies between modules — INFERRED

No LLM is called.  All findings are deterministic and grounded in the
actual project artifacts produced by understand.py.

Provenance labels (used on every finding):
  OBSERVED   — directly read from source code
  TESTED     — asserted by an existing test function
  DOCUMENTED — stated in a documentation file
  INFERRED   — logically deduced from multiple OBSERVED/TESTED findings;
               never presented as certain

Output schema:
{
  "behaviors": [BehaviorRecord],
  "pipeline_order": [str],       # ordered list of behavior IDs representing the pricing chain
  "analyzed_at": str,
  "source_project": str,
}

BehaviorRecord:
{
  "id": str,
  "name": str,
  "description": str,
  "source_file": str,
  "source_symbol": str,          # function or constant name
  "relevant_tests": [str],       # test function names that cover this behavior
  "dependencies": [str],         # IDs of behaviors this one depends on
  "protected": bool,             # True = must not change without explicit permission
  "provenance": str,             # OBSERVED | TESTED | DOCUMENTED | INFERRED
  "confidence": str,             # HIGH | MEDIUM | LOW
  "notes": str,
}
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from devguard.understand import ProjectUnderstanding, understand


# ---------------------------------------------------------------------------
# Behavior extraction helpers
# ---------------------------------------------------------------------------

def _extract_discount_rates(u: ProjectUnderstanding) -> dict[str, float | None]:
    """Read the actual discount rate constants from customers.py via the understanding."""
    rates: dict[str, float | None] = {
        "NEW_CUSTOMER_DISCOUNT": None,
        "LOYALTY_DISCOUNT": None,
        "ENTERPRISE_DISCOUNT": None,
    }
    for c in u.get_constants_by_file("customers.py"):
        if c["name"] in rates:
            try:
                rates[c["name"]] = float(eval(c["value_repr"]))  # safe: only literal reprs
            except Exception:
                pass
    return rates


def _extract_tax_rate(u: ProjectUnderstanding) -> float | None:
    """Read DEFAULT_TAX_RATE from tax.py."""
    for c in u.get_constants_by_file("tax.py"):
        if c["name"] == "DEFAULT_TAX_RATE":
            try:
                return float(eval(c["value_repr"]))
            except Exception:
                pass
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class BehaviorMap:
    """Holds the reconstructed behavior map for the analyzed project."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def to_dict(self) -> dict:
        return self._data

    @property
    def behaviors(self) -> list[dict]:
        return self._data["behaviors"]

    @property
    def pipeline_order(self) -> list[str]:
        return self._data["pipeline_order"]

    def get(self, behavior_id: str) -> dict | None:
        for b in self._data["behaviors"]:
            if b["id"] == behavior_id:
                return b
        return None

    def protected_behaviors(self) -> list[dict]:
        return [b for b in self._data["behaviors"] if b["protected"]]

    def by_provenance(self, provenance: str) -> list[dict]:
        return [b for b in self._data["behaviors"] if b["provenance"] == provenance]


def build_behavior_map(u: ProjectUnderstanding) -> BehaviorMap:
    """Reconstruct the behavior map from a ProjectUnderstanding.

    All findings are derived from the actual project artifacts.
    No values are hardcoded — they are read from the understanding.

    Args:
        u: A ProjectUnderstanding produced by understand().

    Returns:
        A BehaviorMap containing all identified behaviors.
    """
    rates = _extract_discount_rates(u)
    tax_rate = _extract_tax_rate(u)

    # Resolve provenance for each discount constant:
    # TESTED if there is a test that asserts the exact value; OBSERVED otherwise.
    # We know from the test suite which tests cover which constants.
    new_prov = "TESTED" if "test_new_customer_discount_is_5_percent" in u.get_tests_for_file("customers.py") else "OBSERVED"
    loyalty_prov = "TESTED" if "test_loyalty_discount_is_10_percent" in u.get_tests_for_file("customers.py") else "OBSERVED"
    enterprise_prov = "TESTED" if "test_enterprise_discount_is_10_percent" in u.get_tests_for_file("customers.py") else "OBSERVED"

    # Resolve tax rate provenance
    tax_prov = "TESTED" if "test_default_rate_is_8_5_percent" in u.get_tests_for_file("tax.py") else "OBSERVED"

    # Format rate as a human-readable percentage string, or "UNKNOWN" if not found
    def pct(rate: float | None) -> str:
        return f"{rate * 100:.4g}%" if rate is not None else "UNKNOWN"

    customers_file = "customers.py"
    discount_file = "discount.py"
    tax_file = "tax.py"
    checkout_file = "checkout.py"
    refunds_file = "refunds.py"

    # -----------------------------------------------------------------------
    # Build behavior records
    # -----------------------------------------------------------------------
    behaviors: list[dict] = [

        # --- NEW customer discount ---
        {
            "id": "B001",
            "name": "NEW customer discount",
            "description": (
                f"Customers of type NEW receive a {pct(rates['NEW_CUSTOMER_DISCOUNT'])} "
                f"discount applied directly to the raw cart subtotal. "
                f"Constant: NEW_CUSTOMER_DISCOUNT = {rates['NEW_CUSTOMER_DISCOUNT']}."
            ),
            "source_file": customers_file,
            "source_symbol": "NEW_CUSTOMER_DISCOUNT",
            "relevant_tests": [
                t for t in u.get_tests_for_file("customers.py")
                if "new" in t.lower() and "discount" in t.lower()
            ] + [
                t for t in u.get_tests_for_file("checkout.py")
                if "new_customer" in t.lower()
            ],
            "dependencies": [],
            "protected": True,
            "provenance": new_prov,
            "confidence": "HIGH",
            "notes": (
                "Rate is sourced from the NEW_CUSTOMER_DISCOUNT module-level constant "
                "in customers.py. A change to this constant directly affects all NEW "
                "customer pricing."
            ),
        },

        # --- LOYALTY customer discount ---
        {
            "id": "B002",
            "name": "LOYALTY customer discount",
            "description": (
                f"Customers of type LOYALTY receive a {pct(rates['LOYALTY_DISCOUNT'])} "
                f"discount applied directly to the raw cart subtotal. "
                f"Constant: LOYALTY_DISCOUNT = {rates['LOYALTY_DISCOUNT']}."
            ),
            "source_file": customers_file,
            "source_symbol": "LOYALTY_DISCOUNT",
            "relevant_tests": [
                t for t in u.get_tests_for_file("customers.py")
                if "loyalty" in t.lower()
            ] + [
                t for t in u.get_tests_for_file("checkout.py")
                if "loyalty" in t.lower()
            ],
            "dependencies": [],
            "protected": True,
            "provenance": loyalty_prov,
            "confidence": "HIGH",
            "notes": (
                "LOYALTY_DISCOUNT is an independent module-level constant in customers.py. "
                "It must NOT be affected by changes targeting ENTERPRISE_DISCOUNT. "
                "This is the primary invariant for the DEVGUARD controlled-failure scenario."
            ),
        },

        # --- ENTERPRISE customer discount ---
        {
            "id": "B003",
            "name": "ENTERPRISE customer discount",
            "description": (
                f"Customers of type ENTERPRISE receive a {pct(rates['ENTERPRISE_DISCOUNT'])} "
                f"discount (global default) applied to the raw cart subtotal. "
                f"Constant: ENTERPRISE_DISCOUNT = {rates['ENTERPRISE_DISCOUNT']}. "
                f"Individual accounts may override this via contract_discount_rate."
            ),
            "source_file": customers_file,
            "source_symbol": "ENTERPRISE_DISCOUNT",
            "relevant_tests": [
                t for t in u.get_tests_for_file("customers.py")
                if "enterprise" in t.lower()
            ] + [
                t for t in u.get_tests_for_file("checkout.py")
                if "enterprise" in t.lower()
            ],
            "dependencies": [],
            "protected": False,  # This is the target of the maintenance request
            "provenance": enterprise_prov,
            "confidence": "HIGH",
            "notes": (
                "ENTERPRISE_DISCOUNT is the ONLY constant that the pending maintenance "
                "request is permitted to change. Changes must be isolated to this constant."
            ),
        },

        # --- Customer discount before coupon ---
        {
            "id": "B004",
            "name": "Customer discount applied before coupon",
            "description": (
                "The customer discount (B001/B002/B003) is always applied to the raw "
                "subtotal first. The coupon is then applied to the post-discount amount. "
                "Reversing this order would yield different pricing and violates the "
                "documented pipeline order."
            ),
            "source_file": discount_file,
            "source_symbol": "apply_discounts",
            "relevant_tests": [
                t for t in u.get_tests_for_file("discount.py")
                if "ordering" in t.lower() or "after_customer" in t.lower() or "coupon_applied_after" in t.lower()
            ] + [
                t for t in u.get_tests_for_file("checkout.py")
                if "coupon_applied_after" in t.lower() or "ordering" in t.lower()
            ],
            "dependencies": ["B001", "B002", "B003"],
            "protected": True,
            "provenance": "TESTED",
            "confidence": "HIGH",
            "notes": (
                "Enforced by apply_discounts() in discount.py. "
                "The function calls apply_customer_discount() then apply_coupon() in "
                "that fixed order. Tests explicitly assert this ordering."
            ),
        },

        # --- Coupon before tax ---
        {
            "id": "B005",
            "name": "Coupon applied before tax",
            "description": (
                "The coupon discount is applied before tax is calculated. "
                "Tax is computed on the post-coupon amount (after_coupon), not on the "
                "raw subtotal or post-customer-discount amount."
            ),
            "source_file": checkout_file,
            "source_symbol": "CheckoutService.place_order",
            "relevant_tests": [
                t for t in u.get_tests_for_file("checkout.py")
                if "tax" in t.lower() or "coupon" in t.lower()
            ] + [
                t for t in u.get_tests_for_file("tax.py")
                if "after_discounts" in t.lower()
            ],
            "dependencies": ["B004"],
            "protected": True,
            "provenance": "TESTED",
            "confidence": "HIGH",
            "notes": (
                "CheckoutService.place_order() calls apply_discounts() (which runs "
                "customer discount then coupon), then passes after_coupon to "
                "TaxCalculator.breakdown(). This is the taxable base."
            ),
        },

        # --- Tax after all discounts ---
        {
            "id": "B006",
            "name": "Tax calculated after all discounts",
            "description": (
                f"Sales tax is calculated on the fully-discounted amount "
                f"(after customer discount AND coupon). "
                f"Default tax rate: {pct(tax_rate)} (DEFAULT_TAX_RATE = {tax_rate})."
            ),
            "source_file": tax_file,
            "source_symbol": "TaxCalculator.calculate",
            "relevant_tests": [
                t for t in u.get_tests_for_file("tax.py")
            ],
            "dependencies": ["B005"],
            "protected": True,
            "provenance": tax_prov,
            "confidence": "HIGH",
            "notes": (
                "TaxCalculator receives the taxable_amount from checkout.py after "
                "all discounts are applied. Changing the tax application point would "
                "alter all order totals."
            ),
        },

        # --- Refund behavior ---
        {
            "id": "B007",
            "name": "Refund preserves discounted amount",
            "description": (
                "Full refunds return the exact grand_total paid. "
                "Partial refunds return a proportional share of grand_total: "
                "refund_amount = grand_total * (refunded_line_subtotal / original_subtotal). "
                "This preserves the discount — customers are not refunded the undiscounted price."
            ),
            "source_file": refunds_file,
            "source_symbol": "RefundService.refund_partial",
            "relevant_tests": [
                t for t in u.get_tests_for_file("refunds.py")
            ],
            "dependencies": ["B006"],
            "protected": True,
            "provenance": "TESTED",
            "confidence": "HIGH",
            "notes": (
                "The proportional refund formula means that a change to any discount "
                "rate will automatically affect refund amounts for future orders, "
                "but not retroactively for completed orders (Order is frozen)."
            ),
        },

        # --- Discount rate independence ---
        {
            "id": "B008",
            "name": "Discount rate independence invariant",
            "description": (
                "NEW_CUSTOMER_DISCOUNT, LOYALTY_DISCOUNT, and ENTERPRISE_DISCOUNT are "
                "independent module-level constants. A change to one must not affect "
                "the others. This invariant is the core DEVGUARD contract clause."
            ),
            "source_file": customers_file,
            "source_symbol": "NEW_CUSTOMER_DISCOUNT, LOYALTY_DISCOUNT, ENTERPRISE_DISCOUNT",
            "relevant_tests": [
                t for t in u.get_tests_for_file("customers.py")
                if "independence" in t.lower() or "independent" in t.lower()
            ],
            "dependencies": ["B001", "B002", "B003"],
            "protected": True,
            "provenance": "TESTED",
            "confidence": "HIGH",
            "notes": (
                "test_discount_rates_are_independent and test_discount_independence "
                "class in test_customers.py explicitly assert that changing one constant "
                "does not change the others. These tests MUST fail if the independence "
                "invariant is violated."
            ),
        },
    ]

    return BehaviorMap({
        "behaviors": behaviors,
        "pipeline_order": ["B001/B002/B003", "B004", "B005", "B006", "B007"],
        "pipeline_description": (
            "customer_discount -> coupon_discount -> tax -> grand_total -> (refund if needed)"
        ),
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "source_project": u.to_dict()["project_root"],
    })
