"""
tax.py — Tax calculation for LegacyShop.

Tax is calculated on the post-discount amount (after both customer discount
and coupon have been applied).  This is the taxable base.

A flat sales-tax rate is used for simplicity.  The default rate is 8.5%.
Tax is always rounded to 2 decimal places.
"""

from __future__ import annotations

# Default sales-tax rate (8.5%).  Adjustable via TaxCalculator.
DEFAULT_TAX_RATE: float = 0.085


class TaxCalculator:
    """Calculates sales tax on a taxable amount."""

    def __init__(self, rate: float = DEFAULT_TAX_RATE) -> None:
        if not (0.0 <= rate <= 1.0):
            raise ValueError(f"Tax rate must be in [0.0, 1.0], got {rate}")
        self.rate = rate

    def calculate(self, taxable_amount: float) -> float:
        """Return the tax amount for a given taxable total.

        Args:
            taxable_amount: The amount after all discounts have been applied.

        Returns:
            Tax amount in dollars, rounded to 2 decimal places.
        """
        if taxable_amount < 0:
            raise ValueError(f"taxable_amount must be >= 0, got {taxable_amount}")
        return round(taxable_amount * self.rate, 2)

    def total_with_tax(self, taxable_amount: float) -> float:
        """Return taxable_amount + tax, rounded to 2 decimal places."""
        return round(taxable_amount + self.calculate(taxable_amount), 2)

    def breakdown(self, taxable_amount: float) -> dict:
        """Return a full tax breakdown dict.

        Keys:
            taxable_amount: the input
            tax_rate:       the rate used
            tax_amount:     computed tax
            grand_total:    taxable_amount + tax_amount
        """
        tax_amount = self.calculate(taxable_amount)
        return {
            "taxable_amount": taxable_amount,
            "tax_rate": self.rate,
            "tax_amount": tax_amount,
            "grand_total": round(taxable_amount + tax_amount, 2),
        }
