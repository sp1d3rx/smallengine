"""Parts inventory domain contexts."""
from ..gantrika.context import BaseContext
from ..roles.base import cast
from ..roles.parts_roles import StockableRole


class StockAdjustmentContext(BaseContext):
    """Manually adjust stock quantity (physical count correction, write-off, manual fix)."""

    def __init__(self, db, part_row):
        super().__init__(db)
        self.part = cast(part_row, StockableRole, table_name="part")

    def execute(self, delta: int, reason: str, reference_id: int = None) -> dict:
        with self.transaction():
            new_qty = self.part.adjust_stock(self.db, delta, reason, reference_id)
            return {
                "part_id": self.part.id,
                "delta": delta,
                "qty_on_hand": new_qty,
                "is_low_stock": self.part.is_low_stock(),
            }


class ReceiveStockContext(BaseContext):
    """Receive a shipment of parts into inventory."""

    def __init__(self, db, part_row):
        super().__init__(db)
        self.part = cast(part_row, StockableRole, table_name="part")

    def execute(self, quantity: int, reference_id: int = None, unit_cost: float = None) -> dict:
        with self.transaction():
            new_qty = self.part.receive(self.db, quantity, reference_id, unit_cost=unit_cost)
            return {
                "part_id": self.part.id,
                "quantity_received": quantity,
                "qty_on_hand": new_qty,
            }


class LowStockReportContext(BaseContext):
    """Return all active parts at or below their reorder point."""

    def execute(self) -> list:
        rows = self.db(
            (self.db.part.active == True)
            & (self.db.part.qty_on_hand <= self.db.part.reorder_point)
        ).select(orderby=self.db.part.description)
        return [r.as_dict() for r in rows]
