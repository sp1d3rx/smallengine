"""
Roles that a WorkOrder data object can play.
Each role is a pure mixin — no db access in __init__, only in methods.
"""
from decimal import Decimal
from datetime import date


# ── Status pipeline ───────────────────────────────────────────────────────────
# Main forward path. awaiting_parts ↔ in_repair is handled separately.
_TRANSITIONS = {
    "intake":             "diagnosed",
    "diagnosed":          "awaiting_approval",
    "awaiting_approval":  "in_repair",
    "awaiting_parts":     "in_repair",
    "in_repair":          "ready",
    "ready":              "closed",
}


class DiagnosableRole:
    """A work order being evaluated by a technician."""

    def record_diagnosis(self, db, diagnosis_text: str, estimated_cost: Decimal):
        """Persist diagnosis notes and cost estimate."""
        db(db.work_order.id == self.id).update(
            diagnosis=diagnosis_text,
            estimated_cost=float(estimated_cost),
        )


class ProgressableRole:
    """A work order moving through the repair pipeline."""

    def can_advance(self) -> bool:
        return self.status in _TRANSITIONS

    def next_status(self) -> str:
        return _TRANSITIONS.get(self.status)

    def advance(self, db) -> str:
        """Move to the next status in the pipeline."""
        if not self.can_advance():
            raise ValueError(f"Cannot advance work order in status '{self.status}'")
        new_status = self.next_status()
        update = {"status": new_status}
        db(db.work_order.id == self.id).update(**update)
        self.status = new_status  # keep in-memory state in sync with DB
        return new_status

    def request_approval(self, db) -> str:
        """Move diagnosed → awaiting_approval (customer contact needed)."""
        if self.status != "diagnosed":
            raise ValueError(f"Expected 'diagnosed', got '{self.status}'")
        db(db.work_order.id == self.id).update(status="awaiting_approval")
        self.status = "awaiting_approval"
        return "awaiting_approval"

    def approve(self, db) -> str:
        """Customer approved — move awaiting_approval → in_repair."""
        if self.status != "awaiting_approval":
            raise ValueError(f"Expected 'awaiting_approval', got '{self.status}'")
        import datetime
        db(db.work_order.id == self.id).update(
            status="in_repair",
            customer_approved=True,
            approval_date=datetime.datetime.utcnow(),
        )
        self.status = "in_repair"
        return "in_repair"

    def need_parts(self, db) -> str:
        """Flag that parts must be ordered — in_repair → awaiting_parts."""
        if self.status != "in_repair":
            raise ValueError(f"Expected 'in_repair', got '{self.status}'")
        db(db.work_order.id == self.id).update(status="awaiting_parts")
        self.status = "awaiting_parts"
        return "awaiting_parts"

    def parts_arrived(self, db) -> str:
        """Parts received — awaiting_parts → in_repair."""
        if self.status != "awaiting_parts":
            raise ValueError(f"Expected 'awaiting_parts', got '{self.status}'")
        db(db.work_order.id == self.id).update(status="in_repair")
        self.status = "in_repair"
        return "in_repair"

    def cancel(self, db, reason: str = "other", detail: str = "") -> str:
        """Cancel the work order, recording why."""
        db(db.work_order.id == self.id).update(
            status="cancelled",
            cancel_reason=reason,
            cancel_reason_detail=detail,
        )
        self.status = "cancelled"
        return "cancelled"


class NotifiableRole:
    """A work order whose customer needs to be informed it is ready."""

    def mark_customer_notified(self, db) -> None:
        """Record timestamp of customer notification (unit ready)."""
        import datetime
        db(db.work_order.id == self.id).update(
            customer_notified_at=datetime.datetime.utcnow(),
        )

    def set_expected_pickup(self, db, pickup_date: date) -> None:
        """Record the date the customer said they will pick up."""
        db(db.work_order.id == self.id).update(date_expected_pickup=pickup_date)


class BillableWorkRole:
    """A work order being totaled for invoicing, warranty-aware per line."""

    def labor_total(self, db) -> Decimal:
        rows = db(db.work_order_labor.work_order_id == self.id).select(
            db.work_order_labor.total
        )
        return sum(Decimal(str(r.total or 0)) for r in rows)

    def parts_total(self, db) -> Decimal:
        rows = db(db.work_order_part.work_order_id == self.id).select(
            db.work_order_part.total
        )
        return sum(Decimal(str(r.total or 0)) for r in rows)

    def warranty_labor_total(self, db) -> Decimal:
        """Sum of labor lines flagged as warranty-covered."""
        rows = db(
            (db.work_order_labor.work_order_id == self.id)
            & (db.work_order_labor.is_warranty == True)
        ).select(db.work_order_labor.total)
        return sum(Decimal(str(r.total or 0)) for r in rows)

    def warranty_parts_total(self, db) -> Decimal:
        """Sum of parts lines flagged as warranty-covered."""
        rows = db(
            (db.work_order_part.work_order_id == self.id)
            & (db.work_order_part.is_warranty == True)
        ).select(db.work_order_part.total)
        return sum(Decimal(str(r.total or 0)) for r in rows)

    def subtotal(self, db) -> Decimal:
        return self.labor_total(db) + self.parts_total(db)

    def tax_amount(self, db, tax_rate: Decimal) -> Decimal:
        # Texas: tax on parts only, not labor
        return self.parts_total(db) * tax_rate

    def grand_total(self, db, tax_rate: Decimal) -> Decimal:
        return self.subtotal(db) + self.tax_amount(db, tax_rate)

    def customer_owes(self, db, tax_rate: Decimal) -> Decimal:
        """Grand total minus warranty-covered lines (parts tax still applies to non-warranty parts)."""
        warranty_labor = self.warranty_labor_total(db)
        warranty_parts = self.warranty_parts_total(db)
        # Tax applies only to non-warranty parts
        non_warranty_parts = self.parts_total(db) - warranty_parts
        tax = non_warranty_parts * tax_rate
        customer_labor = self.labor_total(db) - warranty_labor
        return max(Decimal("0"), customer_labor + non_warranty_parts + tax)


class WarrantyEligibleRole:
    """A work order that may have manufacturer-covered lines."""

    def mark_as_warranty(self, db, manufacturer_id: int) -> None:
        db(db.work_order.id == self.id).update(manufacturer_id=manufacturer_id)

    def warranty_claim(self, db):
        return db(db.warranty_claim.work_order_id == self.id).select().first()
