"""Purchasing domain contexts: create POs, receive lines, cancel, add/delete lines."""
import datetime
from decimal import Decimal
from ..gantrika.context import BaseContext, ValidationError, BusinessRuleError
from ..roles.base import cast
from ..roles.parts_roles import StockableRole


def _next_po_number(db) -> str:
    """Generate next sequential PO number for the current year."""
    year = datetime.date.today().year
    prefix = f"PO-{year}-"
    existing = db(db.purchase_order.po_number.startswith(prefix)).select(
        db.purchase_order.po_number, orderby=~db.purchase_order.po_number
    ).first()
    if existing:
        try:
            seq = int(existing.po_number.split("-")[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:03d}"


class CreatePOContext(BaseContext):
    """Create a purchase order for a supplier with one or more line items."""

    def __init__(self, db, supplier_row):
        super().__init__(db)
        self.supplier = supplier_row

    def execute(self, lines: list, shipping_method: str = None,
                expected_by=None, notes: str = "", po_number: str = None) -> dict:
        if not lines:
            raise ValidationError("At least one line item is required")

        with self.transaction():
            po_num = po_number or _next_po_number(self.db)
            shipping = shipping_method or getattr(self.supplier, "default_shipping", "ups_ground")

            po_id = self.db.purchase_order.insert(
                po_number=po_num,
                supplier_id=self.supplier.id,
                status="draft",
                shipping_method=shipping,
                expected_by=expected_by,
                notes=notes,
                total=0.00,
            )

            total = Decimal("0")
            for line in lines:
                qty = int(line.get("qty_ordered", 1))
                unit_cost = Decimal(str(line.get("unit_cost", "0")))
                line_total = qty * unit_cost
                total += line_total

                description = line.get("description", "")
                part_id = line.get("part_id")
                if not description and part_id:
                    part = self.db.part[part_id]
                    if part:
                        description = f"{part.part_number} — {part.description}"

                self.db.purchase_order_line.insert(
                    po_id=po_id,
                    part_id=part_id,
                    description=description,
                    qty_ordered=qty,
                    unit_cost=float(unit_cost),
                    total_cost=float(line_total),
                    qty_received=0,
                )

            self.db(self.db.purchase_order.id == po_id).update(total=float(total))
            return {"po_id": po_id, "po_number": po_num, "total": float(total)}


class UpdatePOContext(BaseContext):
    """Update PO header fields and/or mark as sent."""

    def __init__(self, db, po_row):
        super().__init__(db)
        self.po = po_row

    def execute(self, **fields) -> dict:
        with self.transaction():
            allowed = {"shipping_method", "tracking_number", "expected_by",
                       "notes", "status", "ordered_on"}
            update = {k: v for k, v in fields.items() if k in allowed}
            if update:
                self.db(self.db.purchase_order.id == self.po.id).update(**update)
            return {"ok": True}


class ReceivePOLinesContext(BaseContext):
    """Record receipt of one or more PO lines and increment stock via StockableRole."""

    def __init__(self, db, po_row):
        super().__init__(db)
        self.po = po_row

    def execute(self, receipts: list) -> dict:
        if self.po.status in ("received", "cancelled"):
            raise BusinessRuleError(f"Cannot receive on a {self.po.status} PO")

        with self.transaction():
            for r in receipts:
                line = self.db.purchase_order_line[r["line_id"]]
                if not line or line.po_id != self.po.id:
                    continue
                qty = int(r.get("qty_received", 0))
                if qty <= 0:
                    continue
                max_receivable = line.qty_ordered - line.qty_received
                qty = min(qty, max_receivable)
                if qty <= 0:
                    continue

                new_received = line.qty_received + qty
                self.db(self.db.purchase_order_line.id == line.id).update(qty_received=new_received)

                # Increment stock via StockableRole
                if line.part_id:
                    part_row = self.db.part[line.part_id]
                    if part_row:
                        part_role = cast(part_row, StockableRole, table_name="part")
                        part_role.receive(self.db, quantity=qty, reference_id=self.po.id, unit_cost=line.unit_cost)

            # Recompute PO status
            lines = self.db(self.db.purchase_order_line.po_id == self.po.id).select()
            all_received = all(l.qty_received >= l.qty_ordered for l in lines)
            any_received = any(l.qty_received > 0 for l in lines)

            if all_received:
                new_status = "received"
            elif any_received:
                new_status = "partial"
            else:
                new_status = self.po.status

            if new_status != self.po.status:
                self.db(self.db.purchase_order.id == self.po.id).update(status=new_status)

            return {"ok": True, "po_status": new_status}


class CancelPOContext(BaseContext):
    """Cancel a draft or sent PO."""

    def __init__(self, db, po_row):
        super().__init__(db)
        self.po = po_row

    def execute(self) -> dict:
        if self.po.status in ("received", "cancelled"):
            raise BusinessRuleError(f"Cannot cancel a {self.po.status} PO")
        with self.transaction():
            self.db(self.db.purchase_order.id == self.po.id).update(status="cancelled")
            return {"ok": True, "status": "cancelled"}


class AddPOLineContext(BaseContext):
    """Add a line item to an active draft or sent PO."""

    def __init__(self, db, po_row):
        super().__init__(db)
        self.po = po_row

    def execute(self, qty_ordered: int, unit_cost: Decimal,
                part_id: int = None, description: str = "") -> dict:
        if self.po.status not in ("draft", "sent"):
            raise BusinessRuleError("Can only add lines to draft or sent POs")

        with self.transaction():
            line_total = qty_ordered * unit_cost
            if not description and part_id:
                part = self.db.part[part_id]
                if part:
                    description = f"{part.part_number} — {part.description}"

            line_id = self.db.purchase_order_line.insert(
                po_id=self.po.id,
                part_id=part_id,
                description=description,
                qty_ordered=qty_ordered,
                unit_cost=float(unit_cost),
                total_cost=float(line_total),
                qty_received=0,
            )
            # Recalculate total
            lines = self.db(self.db.purchase_order_line.po_id == self.po.id).select()
            new_total = sum(l.total_cost or 0 for l in lines)
            self.db(self.db.purchase_order.id == self.po.id).update(total=new_total)
            return {"id": line_id}


class DeletePOLineContext(BaseContext):
    """Remove a line item from a draft PO."""

    def __init__(self, db, po_row):
        super().__init__(db)
        self.po = po_row

    def execute(self, line_id: int) -> dict:
        if self.po.status != "draft":
            raise BusinessRuleError("Can only remove lines from draft POs")

        with self.transaction():
            self.db(
                (self.db.purchase_order_line.id == line_id)
                & (self.db.purchase_order_line.po_id == self.po.id)
            ).delete()
            lines = self.db(self.db.purchase_order_line.po_id == self.po.id).select()
            new_total = sum(l.total_cost or 0 for l in lines)
            self.db(self.db.purchase_order.id == self.po.id).update(total=new_total)
            return {"ok": True}
