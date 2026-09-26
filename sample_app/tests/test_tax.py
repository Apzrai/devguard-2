"""
test_tax.py — Tests for tax calculation.

Business rules under test:
  - Tax is calculated on the post-discount amount (after customer discount + coupon).
  - Default tax rate is 8.5%.
  - Tax is rounded to 2 decimal places.
  - grand_total = taxable_amount + tax_amount.
"""

import pytest
from sample_app.tax import TaxCalculator, DEFAULT_TAX_RATE


class TestTaxRateDefaults:
    def test_default_rate_is_8_5_percent(self):
        assert DEFAULT_TAX_RATE == pytest.approx(0.085)

    def test_calculator_uses_default_rate(self):
        calc = TaxCalculator()
        assert calc.rate == pytest.approx(0.085)


class TestTaxCalculation:
    def test_tax_on_100_dollars(self):
        calc = TaxCalculator(rate=0.085)
        assert calc.calculate(100.00) == pytest.approx(8.50)

    def test_tax_on_zero(self):
        calc = TaxCalculator()
        assert calc.calculate(0.00) == 0.00

    def test_tax_rounds_to_2dp(self):
        # $99.99 × 0.085 = 8.49915 → 8.50
        calc = TaxCalculator(rate=0.085)
        assert calc.calculate(99.99) == pytest.approx(8.50, abs=0.005)

    def test_negative_amount_raises(self):
        calc = TaxCalculator()
        with pytest.raises(ValueError, match="taxable_amount"):
            calc.calculate(-1.00)

    def test_invalid_rate_above_1_raises(self):
        with pytest.raises(ValueError, match="Tax rate"):
            TaxCalculator(rate=1.5)

    def test_invalid_rate_below_0_raises(self):
        with pytest.raises(ValueError, match="Tax rate"):
            TaxCalculator(rate=-0.01)


class TestTotalWithTax:
    def test_total_with_tax_100_dollars(self):
        calc = TaxCalculator(rate=0.085)
        # 100.00 + 8.50 = 108.50
        assert calc.total_with_tax(100.00) == pytest.approx(108.50)

    def test_total_with_tax_zero(self):
        calc = TaxCalculator()
        assert calc.total_with_tax(0.00) == 0.00


class TestTaxBreakdown:
    def test_breakdown_keys_present(self):
        calc = TaxCalculator(rate=0.085)
        result = calc.breakdown(100.00)
        assert "taxable_amount" in result
        assert "tax_rate" in result
        assert "tax_amount" in result
        assert "grand_total" in result

    def test_breakdown_values_correct(self):
        calc = TaxCalculator(rate=0.10)
        result = calc.breakdown(200.00)
        assert result["taxable_amount"] == 200.00
        assert result["tax_rate"] == 0.10
        assert result["tax_amount"] == 20.00
        assert result["grand_total"] == 220.00

    def test_tax_applied_after_discounts_scenario(self):
        """
        End-to-end math check: discounts are applied first, then tax.

        $100 subtotal
        - 10% customer discount → $90.00
        - $10 coupon → $80.00  (taxable base)
        - 8.5% tax on $80.00 = $6.80
        - grand total = $86.80
        """
        from sample_app.discount import apply_discounts, Coupon, CouponType
        coupon = Coupon("SAVE10", CouponType.FIXED, 10.00)
        discount_result = apply_discounts(100.00, 0.10, coupon)
        taxable = discount_result["after_coupon"]
        assert taxable == 80.00

        calc = TaxCalculator(rate=0.085)
        tax_result = calc.breakdown(taxable)
        assert tax_result["tax_amount"] == pytest.approx(6.80)
        assert tax_result["grand_total"] == pytest.approx(86.80)
