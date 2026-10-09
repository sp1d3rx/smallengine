"""
Equipment sales API endpoints.
"""
import datetime
from decimal import Decimal
from py4web import action, request, HTTP
from ..common import db, auth, session, require_user
from ..contexts.sales import SellEquipmentContext


@action("api/sales", method=["GET"])
@action.uses(db, session, auth)
def sales_list():
    require_user()
    sale_id = request.query.get("id", "").strip()
    days = request.query.get("days", "2").strip()

    if sale_id and sale_id.isdigit():
        query = db.sale.id == int(sale_id)
    else:
        query = db.sale.id > 0
        if days != "all":
            try:
                since = datetime.date.today() - datetime.timedelta(days=int(days))
                query &= db.sale.sale_date >= since
            except Exception:
                pass

    rows = db(query).select(
        db.sale.ALL,
        db.customer.first_name,
        db.customer.last_name,
        left=db.customer.on(db.sale.customer_id == db.customer.id),
        orderby=~db.sale.sale_date | ~db.sale.id,
        limitby=(0, 200),
    )

    sales = []
    for r in rows:
        sale = r.sale.as_dict()
        sale["customer_first"] = r.customer.first_name or ""
        sale["customer_last"] = r.customer.last_name or ""
        sales.append(sale)
    return dict(sales=sales)


def _safe_decimal(val, default="0"):
    if val is None or val == "":
        return Decimal(default) if default is not None else None
    try:
        return Decimal(str(val))
    except Exception:
        return Decimal(default) if default is not None else None


@action("api/sales", method=["POST"])
@action.uses(db, session, auth)
def sales_create():
    require_user()
    data = request.json or {}
    customer = db.customer[data.get("customer_id")]
    equipment = db.equipment[data.get("equipment_id")]
    if not customer or not equipment:
        raise HTTP(422, "customer_id and equipment_id required")

    trade_in_row = None
    if data.get("trade_in_equipment_id"):
        trade_in_row = db.equipment[data["trade_in_equipment_id"]]

    ctx = SellEquipmentContext(db, customer, equipment)
    result = ctx.execute(
        sale_price=_safe_decimal(data.get("sale_price"), "0"),
        employee_id=data.get("employee_id"),
        payment_method=data.get("payment_method", "card"),
        trade_in_row=trade_in_row,
        trade_in_value=_safe_decimal(data.get("trade_in_value"), "0"),
        trade_in_disposition=data.get("trade_in_disposition", "renewed"),
    )
    return result


@action("api/sales/<sale_id:int>", method=["GET"])
@action.uses(db, session, auth)
def sales_get(sale_id):
    row = db.sale[sale_id]
    if not row:
        raise HTTP(404)
    return dict(sale=row.as_dict())


# ── Inventory available for sale ───────────────────────────────────────────────
@action("api/inventory", method=["GET"])
@action.uses(db, session, auth)
def inventory_list():
    condition = request.query.get("condition")  # "new_inventory" | "renewed_inventory"
    query = db.equipment.condition.belongs(["new_inventory", "renewed_inventory"])
    if condition:
        query = db.equipment.condition == condition
    rows = db(query).select(orderby=db.equipment.category | db.equipment.make)
    return dict(inventory=[r.as_dict() for r in rows])
