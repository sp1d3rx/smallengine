"""Roles that a Part data object can play."""
from decimal import Decimal


class StockableRole:
    """A part being tracked in inventory."""

    def is_low_stock(self):
        return (self.qty_on_hand or 0) <= (self.reorder_point or 0)

    def adjust_stock(self, db, delta: int, reason: str, reference_id: int = None):
        new_qty = (self.qty_on_hand or 0) + delta
        db(db.part.id == self.id).update(qty_on_hand=new_qty)
        db.stock_adjustment.insert(
            part_id=self.id,
            delta=delta,
            reason=reason,
            reference_id=reference_id,
        )
        return new_qty

    def consume(self, db, quantity: int, work_order_id: int):
        """Decrement stock when used on a work order."""
        return self.adjust_stock(db, -quantity, "work_order", work_order_id)

    def receive(self, db, quantity: int, reference_id: int = None, unit_cost: float = None):
        """Increment stock and update weighted average cost when a purchase order arrives."""
        q_old = max(0, self.qty_on_hand or 0)
        c_old = float(self.cost or 0.0)
        q_new = quantity

        if unit_cost is not None:
            c_new = float(unit_cost)
            total_q = q_old + q_new
            c_avg = ((q_old * c_old) + (q_new * c_new)) / total_q if total_q > 0 else c_new
            db(db.part.id == self.id).update(cost=round(c_avg, 2))

        return self.adjust_stock(db, quantity, "purchase", reference_id)

    def margin(self):
        cost = Decimal(str(self.cost or 0))
        price = Decimal(str(self.price or 0))
        if cost == 0:
            return None
        return ((price - cost) / cost * 100).quantize(Decimal("0.1"))
