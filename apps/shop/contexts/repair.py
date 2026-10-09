"""Repair domain contexts — use cases across the work order lifecycle."""

import math
from datetime import date, timedelta
from decimal import Decimal

from ..gantrika.context import BaseContext, BusinessRuleError
from ..roles.base import cast
from ..roles.customer_roles import EquipmentOwnerRole
from ..roles.equipment_roles import RepairableRole
from ..roles.work_order_roles import (
    DiagnosableRole,
    ProgressableRole,
    BillableWorkRole,
    NotifiableRole,
)
from ..roles.parts_roles import StockableRole
from ..settings import DEFAULT_LABOR_RATE, ESTIMATE_APPROVAL_THRESHOLD, SALES_TAX_RATE


def _add_workdays(start: date, days: int) -> date:
    """Return start + N workdays (Mon–Fri only)."""
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


# ── Intake ────────────────────────────────────────────────────────────────────


class RepairIntakeContext(BaseContext):
    """Customer brings equipment in for service. Validates equipment and calculates promise date."""

    def __init__(self, db, customer_row, equipment_row):
        super().__init__(db)
        self.customer = cast(customer_row, EquipmentOwnerRole, table_name="customer")
        self.equipment = cast(equipment_row, RepairableRole, table_name="equipment")

    def calculate_promise_date(self, work_type: str = "repair") -> date:
        today = date.today()
        active_statuses = [
            "intake",
            "diagnosed",
            "awaiting_approval",
            "in_repair",
            "awaiting_parts",
        ]
        backlog = self.db(self.db.work_order.status.belongs(active_statuses)).count()

        thirty_days_ago = today - timedelta(days=30)
        closed_recently = self.db(
            (self.db.work_order.status == "closed")
            & (self.db.work_order.date_out >= thirty_days_ago)
        ).count()

        daily_throughput = max(closed_recently / 22.0, 0.5)
        complexity = 0.5 if work_type == "maintenance" else 1.5
        days_needed = math.ceil((backlog / daily_throughput) * complexity)
        days_needed = max(1, min(days_needed, 30))

        return _add_workdays(today, days_needed)

    def execute(
        self,
        reported_problem: str,
        work_type: str = "repair",
        employee_id: int = None,
        date_promised: date = None,
        notes: str = "",
        pre_approved_limit: Decimal = None,
        estimated_cost: Decimal = None,
    ) -> int:
        if not self.equipment.is_customer_owned():
            raise BusinessRuleError("Equipment is shop inventory, not customer-owned")

        if not date_promised:
            date_promised = self.calculate_promise_date(work_type)

        with self.transaction():
            wo_id = self.db.work_order.insert(
                customer_id=self.customer.id,
                equipment_id=self.equipment.id,
                employee_id=employee_id,
                work_type=work_type,
                reported_problem=reported_problem,
                status="intake",
                date_in=date.today(),
                date_promised=date_promised,
                customer_approved=False,
                notes=notes,
                pre_approved_limit=pre_approved_limit,
                estimated_cost=estimated_cost,
            )
            return wo_id


# ── Diagnosis ─────────────────────────────────────────────────────────────────


class DiagnoseRepairContext(BaseContext):
    """Technician records diagnosis and estimate; checks if approval is required."""

    def __init__(self, db, work_order_row):
        super().__init__(db)
        self.work_order = cast(
            work_order_row, DiagnosableRole, ProgressableRole, table_name="work_order"
        )

    def execute(self, diagnosis: str, estimated_cost: Decimal) -> dict:
        with self.transaction():
            wo = self.work_order
            wo.record_diagnosis(self.db, diagnosis, estimated_cost)
            wo.advance(self.db)  # intake → diagnosed

            needs_approval = estimated_cost > Decimal(str(ESTIMATE_APPROVAL_THRESHOLD))
            if needs_approval:
                wo.request_approval(self.db)  # diagnosed → awaiting_approval
                new_status = "awaiting_approval"
            else:
                new_status = "diagnosed"

            return {
                "work_order_id": wo.id,
                "status": new_status,
                "needs_customer_approval": needs_approval,
                "estimated_cost": float(estimated_cost),
            }


# ── Approval ──────────────────────────────────────────────────────────────────


class RecordApprovalContext(BaseContext):
    """Customer approves or declines the repair estimate."""

    def __init__(self, db, work_order_row):
        super().__init__(db)
        self.work_order = cast(
            work_order_row, ProgressableRole, table_name="work_order"
        )

    def execute(
        self,
        approved: bool,
        decline_reason: str = "customer_declined",
        decline_detail: str = "",
    ) -> dict:
        with self.transaction():
            wo = self.work_order
            if approved:
                new_status = wo.approve(self.db)  # awaiting_approval → in_repair
            else:
                new_status = wo.cancel(
                    self.db, reason=decline_reason, detail=decline_detail
                )
            return {"approved": approved, "status": new_status}


# ── Cancel ────────────────────────────────────────────────────────────────────


class CancelRepairContext(BaseContext):
    """Cancel a work order with documented reasons."""

    def __init__(self, db, work_order_row):
        super().__init__(db)
        self.work_order = cast(
            work_order_row, ProgressableRole, table_name="work_order"
        )

    def execute(self, reason: str, detail: str = "") -> dict:
        with self.transaction():
            new_status = self.work_order.cancel(self.db, reason=reason, detail=detail)
            return {"status": new_status}


# ── Parts availability ────────────────────────────────────────────────────────


class NeedPartsContext(BaseContext):
    """Tech flags that parts are awaited."""

    def __init__(self, db, work_order_row):
        super().__init__(db)
        self.work_order = cast(
            work_order_row, ProgressableRole, table_name="work_order"
        )

    def execute(self) -> dict:
        with self.transaction():
            new_status = self.work_order.need_parts(self.db)
            return {"status": new_status}


class PartsArrivedContext(BaseContext):
    """Parts arrived — resume repair."""

    def __init__(self, db, work_order_row):
        super().__init__(db)
        self.work_order = cast(
            work_order_row, ProgressableRole, table_name="work_order"
        )

    def execute(self) -> dict:
        with self.transaction():
            new_status = self.work_order.parts_arrived(self.db)
            return {"status": new_status}


# ── Labor / Parts lines ───────────────────────────────────────────────────────


class AddLaborContext(BaseContext):
    """Add a labor line to an open work order."""

    def __init__(self, db, work_order_row):
        super().__init__(db)
        self.work_order = work_order_row

    def execute(
        self,
        description: str,
        hours: Decimal,
        rate: Decimal = None,
        employee_id: int = None,
        is_warranty: bool = False,
    ) -> int:
        if rate is None:
            rate = Decimal(str(DEFAULT_LABOR_RATE))
        total = hours * rate
        with self.transaction():
            line_id = self.db.work_order_labor.insert(
                work_order_id=self.work_order.id,
                employee_id=employee_id,
                description=description,
                hours=float(hours),
                rate=float(rate),
                total=float(total),
                is_warranty=is_warranty,
            )
            return line_id


class AddPartContext(BaseContext):
    """Add a parts line to an open work order and consume stock via StockableRole."""

    def __init__(self, db, work_order_row):
        super().__init__(db)
        self.work_order = work_order_row

    def execute(
        self,
        quantity: int,
        unit_price: Decimal,
        part_id: int = None,
        description: str = None,
        unit_cost: Decimal = None,
        is_warranty: bool = False,
    ) -> int:
        with self.transaction():
            if part_id:
                part_row = self.db.part[part_id]
                if part_row:
                    stockable = cast(part_row, StockableRole, table_name="part")
                    description = description or part_row.description
                    if unit_cost is None:
                        unit_cost = Decimal(str(part_row.cost))

                    # If already present on work order, increment quantity
                    existing = (
                        self.db(
                            (
                                self.db.work_order_part.work_order_id
                                == self.work_order.id
                            )
                            & (self.db.work_order_part.part_id == part_id)
                        )
                        .select()
                        .first()
                    )
                    if existing:
                        new_qty = existing.quantity + quantity
                        new_total = Decimal(str(new_qty)) * Decimal(
                            str(existing.unit_price)
                        )
                        stockable.consume(self.db, quantity, self.work_order.id)
                        self.db.work_order_part[existing.id] = dict(
                            quantity=new_qty,
                            total=float(new_total),
                        )
                        return existing.id

                    stockable.consume(self.db, quantity, self.work_order.id)

            total = Decimal(str(quantity)) * unit_price
            line_id = self.db.work_order_part.insert(
                work_order_id=self.work_order.id,
                part_id=part_id,
                description=description,
                quantity=quantity,
                unit_cost=float(unit_cost or 0),
                unit_price=float(unit_price),
                total=float(total),
                is_warranty=is_warranty,
            )
            return line_id


# ── Close ─────────────────────────────────────────────────────────────────────


class GenerateInvoiceContext(BaseContext):
    """Generate (or retrieve) an invoice for a work order without closing it."""

    def __init__(self, db, work_order_row):
        super().__init__(db)
        self.work_order = cast(
            work_order_row, BillableWorkRole, table_name="work_order"
        )

    def execute(self) -> dict:
        tax_rate = Decimal(str(SALES_TAX_RATE))
        existing = (
            self.db(self.db.invoice.work_order_id == self.work_order.id)
            .select()
            .first()
        )
        if existing:
            return {"invoice_id": existing.id, "already_existed": True}

        with self.transaction():
            subtotal = self.work_order.subtotal(self.db)
            tax = self.work_order.tax_amount(self.db, tax_rate)
            customer_amount = self.work_order.customer_owes(self.db, tax_rate)

            inv_status = "paid" if customer_amount == 0 else "draft"
            invoice_id = self.db.invoice.insert(
                work_order_id=self.work_order.id,
                customer_id=self.db.work_order[self.work_order.id].customer_id,
                subtotal=float(subtotal),
                tax_amount=float(tax),
                total=float(customer_amount),
                status=inv_status,
            )
            return {"invoice_id": invoice_id, "already_existed": False}


class CloseRepairContext(BaseContext):
    """Close a ready work order after ensuring invoice is generated and paid."""

    def __init__(self, db, work_order_row):
        super().__init__(db)
        self.work_order = cast(
            work_order_row, ProgressableRole, table_name="work_order"
        )

    def execute(self) -> dict:
        if self.work_order.status != "ready":
            raise BusinessRuleError(
                f"Work order must be 'ready' to close (got '{self.work_order.status}')"
            )
        invoice = (
            self.db(self.db.invoice.work_order_id == self.work_order.id)
            .select()
            .first()
        )
        if not invoice:
            raise BusinessRuleError("Generate invoice before closing")
        if invoice.status != "paid":
            raise BusinessRuleError("Invoice must be fully paid before closing")

        with self.transaction():
            self.work_order.advance(self.db)  # ready → closed
            return {"status": "closed"}


# ── Customer ready notification ───────────────────────────────────────────────


class NotifyReadyContext(BaseContext):
    """Record that customer was notified their unit is ready for pickup."""

    def __init__(self, db, work_order_row):
        super().__init__(db)
        self.work_order = cast(work_order_row, NotifiableRole, table_name="work_order")

    def execute(self, pickup_date: date = None) -> dict:
        with self.transaction():
            self.work_order.mark_customer_notified(self.db)
            if pickup_date:
                self.work_order.set_expected_pickup(self.db, pickup_date)
            return {"ok": True}
