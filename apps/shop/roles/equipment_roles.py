"""
Roles that an Equipment data object can play.
"""
from decimal import Decimal


class RepairableRole:
    """
    Equipment brought in for service — knows its repair history
    and whether it is eligible for warranty work.
    """

    def repair_history(self, db):
        return db(db.work_order.equipment_id == self.id).select(
            orderby=~db.work_order.date_in
        )

    def last_service_date(self, db):
        row = db(db.work_order.equipment_id == self.id).select(
            db.work_order.date_out,
            orderby=~db.work_order.date_out,
            limitby=(0, 1),
        ).first()
        return row.date_out if row else None

    def is_customer_owned(self):
        return self.condition == "customer_owned"


class SellableRole:
    """
    Equipment listed in shop inventory ready for sale.
    """

    def is_available(self):
        return self.condition in ("new_inventory", "renewed_inventory")

    def cost_of_goods(self, db):
        """
        For renewed equipment: acquisition cost + any refurb work orders.
        For new stock: acquisition_cost only.
        """
        base = Decimal(str(self.acquisition_cost or 0))
        if self.condition != "renewed_inventory":
            return base

        work_orders = db(db.work_order.equipment_id == self.id).select()
        for wo in work_orders:
            labor = db(db.work_order_labor.work_order_id == wo.id).select()
            parts = db(db.work_order_part.work_order_id == wo.id).select()
            base += sum(Decimal(str(l.total or 0)) for l in labor)
            base += sum(Decimal(str(p.total or 0)) for p in parts)
        return base

    def suggested_margin(self, db, margin_pct=0.30):
        cog = self.cost_of_goods(db)
        return cog * (1 + Decimal(str(margin_pct)))


class TradeInRole:
    """
    Equipment being accepted as a trade-in.
    """

    def assign_to_renewed_inventory(self, db, acquisition_value: Decimal):
        db(db.equipment.id == self.id).update(
            condition="renewed_inventory",
            acquisition_cost=float(acquisition_value),
        )

    def assign_to_scrap(self, db):
        db(db.equipment.id == self.id).update(condition="scrap")
