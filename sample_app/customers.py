"""
customers.py — Customer model and customer type definitions for LegacyShop.

Customer types:
  NEW        — first-time or unverified customers (5% discount)
  LOYALTY    — returning customers in the loyalty programme (10% discount)
  ENTERPRISE — business accounts on a negotiated contract (10% discount, adjustable)

The ENTERPRISE discount rate is stored as a class-level constant so it can be
updated by a single targeted change — this is the key invariant verified by DEVGUARD.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CustomerType(str, Enum):
    NEW = "NEW"
    LOYALTY = "LOYALTY"
    ENTERPRISE = "ENTERPRISE"


# ---------------------------------------------------------------------------
# Discount rates — one constant per customer type.
# These are the source of truth for DEVGUARD's behavioral contract.
# ---------------------------------------------------------------------------

NEW_CUSTOMER_DISCOUNT: float = 0.05          # 5%  — new customer benefit
LOYALTY_DISCOUNT: float = 0.10               # 10% — loyalty programme rate
ENTERPRISE_DISCOUNT: float = 0.10            # 10% — enterprise contract rate (initial)


def get_customer_discount_rate(customer_type: CustomerType) -> float:
    """Return the discount rate for a given customer type.

    Returns a fraction in [0.0, 1.0].  A rate of 0.10 means 10% off.
    """
    if customer_type == CustomerType.NEW:
        return NEW_CUSTOMER_DISCOUNT
    if customer_type == CustomerType.LOYALTY:
        return LOYALTY_DISCOUNT
    if customer_type == CustomerType.ENTERPRISE:
        return ENTERPRISE_DISCOUNT
    raise ValueError(f"Unknown customer type: {customer_type}")


# ---------------------------------------------------------------------------
# Customer record
# ---------------------------------------------------------------------------

@dataclass
class Customer:
    """Represents a LegacyShop customer."""

    customer_id: str
    name: str
    email: str
    customer_type: CustomerType
    # Optional override for enterprise customers with a bespoke contract rate.
    # When None, the global ENTERPRISE_DISCOUNT constant is used.
    contract_discount_rate: Optional[float] = field(default=None)

    def __post_init__(self) -> None:
        if self.contract_discount_rate is not None:
            if not (0.0 <= self.contract_discount_rate <= 1.0):
                raise ValueError(
                    f"contract_discount_rate must be in [0.0, 1.0], "
                    f"got {self.contract_discount_rate}"
                )
        if self.customer_type != CustomerType.ENTERPRISE and self.contract_discount_rate is not None:
            raise ValueError(
                "contract_discount_rate is only valid for ENTERPRISE customers"
            )

    @property
    def discount_rate(self) -> float:
        """Effective discount rate for this customer.

        Enterprise customers with an explicit contract rate use that rate.
        All others use the global constant for their type.
        """
        if (
            self.customer_type == CustomerType.ENTERPRISE
            and self.contract_discount_rate is not None
        ):
            return self.contract_discount_rate
        return get_customer_discount_rate(self.customer_type)
