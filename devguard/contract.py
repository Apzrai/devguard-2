"""
devguard/contract.py — Behavioral Contract builder.

Constructs a formal behavioral contract from a BehaviorMap and a
MaintenanceRequest.  The contract answers three questions:

  1. What is being asked to change?
  2. What is the current behavior?
  3. What is NOT allowed to change?

No LLM is called.  The contract is built deterministically from the
behavior map, which is itself derived from actual source analysis.

Output schema:
{
  "contract_id": str,
  "created_at": str,
  "maintenance_request": MaintenanceRequest (dict),
  "current_behavior": {behavior_id: description},
  "target_behavior": {description of the permitted change},
  "allowed_change": AllowedChange (dict),
  "protected_behaviors": [ProtectedClause],
  "success_criteria": [str],
  "source_project": str,
}

ProtectedClause:
{
  "behavior_id": str,
  "name": str,
  "invariant": str,       # what must remain true
  "must_not": str,        # what must NOT happen
  "severity": str,        # CRITICAL | HIGH | LOW
  "test_anchors": [str],  # test function names that enforce this clause
}
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from devguard.behavior_map import BehaviorMap


# ---------------------------------------------------------------------------
# Maintenance Request model
# ---------------------------------------------------------------------------

@dataclass
class MaintenanceRequest:
    """A structured maintenance request targeting a specific behavior change."""

    request_id: str
    description: str          # natural-language description
    target_behavior_id: str   # the behavior being changed (e.g. "B003")
    target_symbol: str        # the specific constant/function to change
    target_file: str          # source file containing the symbol
    current_value: str        # current value (human-readable)
    requested_value: str      # requested new value (human-readable)
    requestor: str = "developer"
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "description": self.description,
            "target_behavior_id": self.target_behavior_id,
            "target_symbol": self.target_symbol,
            "target_file": self.target_file,
            "current_value": self.current_value,
            "requested_value": self.requested_value,
            "requestor": self.requestor,
            "notes": self.notes,
        }


@dataclass
class AllowedChange:
    """Precisely scoped change that is permitted."""

    symbol: str          # e.g. "ENTERPRISE_DISCOUNT"
    file: str            # e.g. "customers.py"
    from_value: str      # e.g. "0.10"
    to_value: str        # e.g. "0.15"
    scope_note: str      # plain-language scope description

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "file": self.file,
            "from_value": self.from_value,
            "to_value": self.to_value,
            "scope_note": self.scope_note,
        }


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------

class BehavioralContract:
    """A formal contract governing what may and may not change."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def to_dict(self) -> dict:
        return self._data

    @property
    def contract_id(self) -> str:
        return self._data["contract_id"]

    @property
    def protected_clauses(self) -> list[dict]:
        return self._data["protected_behaviors"]

    @property
    def success_criteria(self) -> list[str]:
        return self._data["success_criteria"]

    @property
    def allowed_change(self) -> dict:
        return self._data["allowed_change"]

    def get_clause(self, behavior_id: str) -> dict | None:
        for c in self._data["protected_behaviors"]:
            if c["behavior_id"] == behavior_id:
                return c
        return None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_contract(
    bmap: BehaviorMap,
    request: MaintenanceRequest,
) -> BehavioralContract:
    """Build a behavioral contract for a given maintenance request.

    All protected clauses are derived from behaviors marked protected=True
    in the behavior map, EXCEPT the behavior targeted by the request.

    Args:
        bmap:    The BehaviorMap for the project being analyzed.
        request: The maintenance request to build the contract around.

    Returns:
        A BehavioralContract ready for use in impact analysis and verification.
    """
    target_behavior = bmap.get(request.target_behavior_id)

    # Current behavior snapshot — just the targeted behavior
    current_behavior = {}
    if target_behavior:
        current_behavior[request.target_behavior_id] = target_behavior["description"]

    # Allowed change — precisely scoped
    allowed_change = AllowedChange(
        symbol=request.target_symbol,
        file=request.target_file,
        from_value=request.current_value,
        to_value=request.requested_value,
        scope_note=(
            f"Only the constant '{request.target_symbol}' in '{request.target_file}' "
            f"may be changed from {request.current_value} to {request.requested_value}. "
            f"No other symbols, files, or behaviors may be modified."
        ),
    )

    # Protected clauses — all protected behaviors EXCEPT the target
    protected_clauses: list[dict] = []
    for b in bmap.protected_behaviors():
        if b["id"] == request.target_behavior_id:
            continue  # this is the one allowed to change

        # Severity: CRITICAL for the independence invariant and pipeline ordering;
        # HIGH for tax and refund; LOW for others
        if b["id"] in ("B008", "B004", "B005"):
            severity = "CRITICAL"
        elif b["id"] in ("B006", "B007"):
            severity = "HIGH"
        else:
            severity = "HIGH"

        # Build the invariant statement and must_not from the behavior description
        if b["id"] == "B001":
            invariant = f"NEW customer discount remains {b['description'].split('%')[0].split()[-1]}% (NEW_CUSTOMER_DISCOUNT unchanged)"
            must_not = "NEW_CUSTOMER_DISCOUNT must not be modified"
        elif b["id"] == "B002":
            invariant = f"LOYALTY customer discount remains {b['description'].split('%')[0].split()[-1]}% (LOYALTY_DISCOUNT unchanged)"
            must_not = "LOYALTY_DISCOUNT must not be modified"
        elif b["id"] == "B004":
            invariant = "Customer discount is always applied before coupon discount"
            must_not = "The ordering of apply_customer_discount() and apply_coupon() must not be swapped"
        elif b["id"] == "B005":
            invariant = "Coupon is always applied before tax is calculated"
            must_not = "Tax must not be computed before coupons are applied"
        elif b["id"] == "B006":
            invariant = "Tax is computed on the fully-discounted amount (after customer discount and coupon)"
            must_not = "The taxable base must not change to a pre-discount amount"
        elif b["id"] == "B007":
            invariant = "Full refund returns grand_total; partial refund is proportional to grand_total"
            must_not = "Refund calculation must not use undiscounted unit prices as the refund base"
        elif b["id"] == "B008":
            invariant = (
                "NEW_CUSTOMER_DISCOUNT, LOYALTY_DISCOUNT, and ENTERPRISE_DISCOUNT "
                "are independent constants; changing one does not affect the others"
            )
            must_not = "A change to ENTERPRISE_DISCOUNT must not alter LOYALTY_DISCOUNT or NEW_CUSTOMER_DISCOUNT"
        else:
            invariant = b["description"]
            must_not = f"Behavior {b['id']} ({b['name']}) must not be altered"

        protected_clauses.append({
            "behavior_id": b["id"],
            "name": b["name"],
            "invariant": invariant,
            "must_not": must_not,
            "severity": severity,
            "test_anchors": b["relevant_tests"],
            "provenance": b["provenance"],
            "source_file": b["source_file"],
            "source_symbol": b["source_symbol"],
        })

    # Success criteria
    success_criteria = [
        f"ENTERPRISE_DISCOUNT is updated from {request.current_value} to {request.requested_value} in {request.target_file}",
        "LOYALTY_DISCOUNT remains unchanged at its current value",
        "NEW_CUSTOMER_DISCOUNT remains unchanged at its current value",
        "All tests in test_customers.py that reference LOYALTY continue to pass",
        "All tests in test_discount.py continue to pass",
        "All tests in test_checkout.py continue to pass",
        "All tests in test_refunds.py continue to pass",
        "The pricing pipeline order (customer discount -> coupon -> tax) is preserved",
    ]

    return BehavioralContract({
        "contract_id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "maintenance_request": request.to_dict(),
        "current_behavior": current_behavior,
        "target_behavior": {
            "description": (
                f"ENTERPRISE_DISCOUNT is changed to {request.requested_value} "
                f"({float(request.requested_value) * 100:.4g}% discount for Enterprise customers). "
                f"All other discount rates and behaviors remain unchanged."
            ),
        },
        "allowed_change": allowed_change.to_dict(),
        "protected_behaviors": protected_clauses,
        "success_criteria": success_criteria,
        "source_project": bmap.to_dict()["source_project"],
    })


# ---------------------------------------------------------------------------
# Canonical maintenance request for the Phase 3 demo scenario
# ---------------------------------------------------------------------------

def make_enterprise_discount_request(current_rate: str = "0.10") -> MaintenanceRequest:
    """Return the canonical Phase 3 maintenance request:
    Update ENTERPRISE_DISCOUNT from 10% to 15%.
    """
    return MaintenanceRequest(
        request_id=str(uuid.uuid4()),
        description="Update the Enterprise discount from 10% to 15%.",
        target_behavior_id="B003",
        target_symbol="ENTERPRISE_DISCOUNT",
        target_file="customers.py",
        current_value=current_rate,
        requested_value="0.15",
        requestor="developer",
        notes=(
            "Matches new commercial pricing policy. "
            "Only ENTERPRISE_DISCOUNT should change. "
            "LOYALTY_DISCOUNT and NEW_CUSTOMER_DISCOUNT must remain unchanged."
        ),
    )
