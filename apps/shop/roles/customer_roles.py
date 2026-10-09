"""
Roles that a Customer data object can play.
"""
from decimal import Decimal


class EquipmentOwnerRole:
    """
    A customer acting as the owner of equipment being serviced.
    Knows how to look up their equipment and open work orders.
    """

    def open_work_orders(self, db):
        return db(
            (db.work_order.customer_id == self.id)
            & db.work_order.status.belongs(
                ["intake", "diagnosed", "awaiting_parts", "in_repair", "ready"]
            )
        ).select(orderby=~db.work_order.created_on)

    def equipment_list(self, db):
        return db(db.equipment.customer_id == self.id).select()

    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class BillableRole:
    """
    A customer in the context of being invoiced.
    Holds balance and payment methods logic.
    """

    def outstanding_balance(self, db):
        rows = db(
            (db.invoice.customer_id == self.id)
            & db.invoice.status.belongs(["sent", "partial"])
        ).select(db.invoice.total, db.invoice.id)

        total_invoiced = sum(r.total or 0 for r in rows)

        payments = db(
            db.payment.invoice_id.belongs([r.id for r in rows])
        ).select(db.payment.amount)

        total_paid = sum(p.amount or 0 for p in payments)
        return Decimal(str(total_invoiced)) - Decimal(str(total_paid))

    def unpaid_invoices(self, db):
        return db(
            (db.invoice.customer_id == self.id)
            & db.invoice.status.belongs(["sent", "partial"])
        ).select(orderby=db.invoice.due_date)
