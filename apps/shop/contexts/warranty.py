"""Warranty claim domain contexts."""
from datetime import date
from decimal import Decimal
from ..gantrika.context import BaseContext, BusinessRuleError
from ..roles.base import cast
from ..roles.work_order_roles import BillableWorkRole, WarrantyEligibleRole


class OpenWarrantyClaimContext(BaseContext):
    """Submit a warranty claim to a manufacturer for a completed warranty work order."""

    def __init__(self, db, work_order_row, manufacturer_row):
        super().__init__(db)
        self.work_order = cast(
            work_order_row,
            BillableWorkRole, WarrantyEligibleRole,
            table_name="work_order",
        )
        self.manufacturer = manufacturer_row

    def execute(self, covered_labor: Decimal, covered_parts: Decimal,
                mfr_claim_number: str = None) -> int:
        if not self.work_order.is_warranty:
            raise BusinessRuleError("Work order is not flagged as warranty work")

        with self.transaction():
            claim_id = self.db.warranty_claim.insert(
                work_order_id=self.work_order.id,
                manufacturer_id=self.manufacturer.id,
                mfr_claim_number=mfr_claim_number,
                submitted_date=date.today(),
                covered_labor=float(covered_labor),
                covered_parts=float(covered_parts),
                status="submitted",
            )
            return claim_id


class RecordWarrantyPaymentContext(BaseContext):
    """Manufacturer reimburses the shop for a warranty claim."""

    def __init__(self, db, warranty_claim_row):
        super().__init__(db)
        self.claim = warranty_claim_row

    def execute(self, amount: Decimal, payment_date: date = None) -> dict:
        payment_date = payment_date or date.today()
        new_status = "paid" if amount > 0 else "denied"

        with self.transaction():
            self.db(self.db.warranty_claim.id == self.claim.id).update(
                reimbursement_amount=float(amount),
                payment_date=payment_date,
                status=new_status,
            )
            return {
                "claim_id": self.claim.id,
                "status": new_status,
                "reimbursement_amount": float(amount),
                "payment_date": str(payment_date),
            }
