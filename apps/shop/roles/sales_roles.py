"""Roles for Sales and Retail POS domain objects."""
from datetime import date
from decimal import Decimal
from ..roles.base import cast
from ..roles.parts_roles import StockableRole

SALES_TAX_RATE = Decimal("0.0825")


class CashRegisterSaleRole:
    """A sale transaction acting as an active cash register / POS checkout session."""

    def recalculate_totals(self, db):
        lines = db(db.sale_line.sale_id == self.id).select()
        subtotal = sum(Decimal(str(line.total or 0)) for line in lines)
        tax = (subtotal * SALES_TAX_RATE).quantize(Decimal("0.01"))
        total = subtotal + tax
        db(db.sale.id == self.id).update(
            subtotal=float(subtotal),
            tax_amount=float(tax),
            total=float(total),
        )
        return {"subtotal": float(subtotal), "tax": float(tax), "total": float(total)}

    def add_item(self, db, part_row, quantity: int = 1):
        if self.status != "open":
            raise ValueError("Sale is not open")
        if (part_row.qty_on_hand or 0) <= 0:
            raise ValueError("Part is out of stock")

        unit_price = Decimal(str(part_row.price or 0))
        unit_cost = Decimal(str(part_row.cost or 0))

        existing = db(
            (db.sale_line.sale_id == self.id) & (db.sale_line.part_id == part_row.id)
        ).select().first()

        if existing:
            new_qty = existing.quantity + quantity
            new_total = Decimal(str(new_qty)) * unit_price
            db(db.sale_line.id == existing.id).update(quantity=new_qty, total=float(new_total))
        else:
            db.sale_line.insert(
                sale_id=self.id,
                part_id=part_row.id,
                description=part_row.description,
                quantity=quantity,
                unit_price=float(unit_price),
                unit_cost=float(unit_cost),
                total=float(Decimal(str(quantity)) * unit_price),
            )

        self.recalculate_totals(db)

    def remove_item(self, db, line_id: int):
        if self.status != "open":
            raise ValueError("Sale is not open")
        line = db(
            (db.sale_line.id == line_id) & (db.sale_line.sale_id == self.id)
        ).select().first()
        if not line:
            raise ValueError("Line item not found")
        db(db.sale_line.id == line_id).delete()
        self.recalculate_totals(db)

    def finalize_payment(self, db, payment_method: str, customer_id: int = None,
                         cash_customer_name: str = None, payment_reference: str = None):
        if self.status != "open":
            raise ValueError("Sale is not open")

        lines = db(db.sale_line.sale_id == self.id).select()
        if not lines:
            raise ValueError("Cannot finalize an empty sale")

        # 1. Decrement inventory via StockableRole
        for line in lines:
            if line.part_id:
                part_row = db.part[line.part_id]
                if part_row:
                    part_role = cast(part_row, StockableRole, table_name="part")
                    part_role.adjust_stock(db, -line.quantity, reason="retail_sale", reference_id=self.id)

        # 2. Update sale status
        db(db.sale.id == self.id).update(
            status="paid",
            payment_method=payment_method,
            customer_id=customer_id,
            cash_customer_name=cash_customer_name,
            notes=payment_reference,
            sale_date=date.today(),
        )

        # 3. Create paid invoice & payment record
        inv_id = db.invoice.insert(
            sale_id=self.id,
            customer_id=customer_id,
            subtotal=self.subtotal,
            tax_amount=self.tax_amount,
            total=self.total,
            status="paid",
        )
        db.payment.insert(
            invoice_id=inv_id,
            amount=self.total,
            method=payment_method,
            reference=payment_reference or f"POS Sale #{self.id}",
            received_on=date.today(),
        )
        return inv_id

    def void(self, db):
        was_paid = self.status == "paid"
        if was_paid:
            lines = db(db.sale_line.sale_id == self.id).select()
            for line in lines:
                if line.part_id:
                    part_row = db.part[line.part_id]
                    if part_row:
                        part_role = cast(part_row, StockableRole, table_name="part")
                        part_role.adjust_stock(db, line.quantity, reason="retail_void", reference_id=self.id)

        db(db.sale.id == self.id).update(status="voided")
        inv = db(db.invoice.sale_id == self.id).select().first()
        if inv:
            db(db.invoice.id == inv.id).update(status="voided")

    def process_return(self, db, return_items: list):
        if self.status != "paid":
            raise ValueError("Can only process returns for paid sales")

        for item in return_items:
            line_id = int(item["line_id"])
            qty = int(item["quantity"])
            if qty <= 0:
                continue
            line = db(
                (db.sale_line.id == line_id) & (db.sale_line.sale_id == self.id)
            ).select().first()
            if not line:
                continue
            if line.part_id:
                part_row = db.part[line.part_id]
                if part_row:
                    part_role = cast(part_row, StockableRole, table_name="part")
                    part_role.adjust_stock(db, qty, reason="return", reference_id=self.id)
