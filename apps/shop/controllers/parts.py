"""
Parts inventory API endpoints.
"""

from py4web import action, request, HTTP
from ..common import db, auth, session
from ..contexts.inventory import (
    StockAdjustmentContext,
    ReceiveStockContext,
    LowStockReportContext,
)


@action("api/parts", method=["GET"])
@action.uses(db, session, auth)
def parts_list():
    low_stock_only = request.query.get("low_stock") == "1"
    q = request.query.get("q", "").strip()
    limit = request.query.get("limit")
    offset = request.query.get("offset")

    if low_stock_only:
        ctx = LowStockReportContext(db)
        return dict(parts=ctx.execute())

    limitby = None
    if limit:
        try:
            off = int(offset or 0)
            limitby = (off, off + int(limit))
        except (TypeError, ValueError):
            limitby = None

    query = db.part.active == True
    if q:
        query &= db.part.part_number.contains(q) | db.part.description.contains(q)
    rows = db(query).select(orderby=db.part.description, limitby=limitby)
    return dict(parts=[r.as_dict() for r in rows])


@action("api/parts", method=["POST"])
@action.uses(db, session, auth)
def parts_create():
    data = request.json or {}
    result = db.part.validate_and_insert(
        **{
            k: data.get(k)
            for k in [
                "part_number",
                "description",
                "manufacturer_id",
                "supplier_id",
                "compatible_categories",
                "qty_on_hand",
                "reorder_point",
                "reorder_qty",
                "cost",
                "price",
            ]
        }
    )
    if result.get("errors"):
        raise HTTP(422, str(result["errors"]))
    return dict(id=result["id"])


@action("api/parts/<part_id:int>", method=["GET"])
@action.uses(db, session, auth)
def parts_get(part_id):
    row = db.part[part_id]
    if not row:
        raise HTTP(404)
    adjustments = db(db.stock_adjustment.part_id == part_id).select(
        orderby=~db.stock_adjustment.created_on, limitby=(0, 20)
    )
    part = row.as_dict()
    if row.supplier_id:
        sup = db.supplier[row.supplier_id]
        part["supplier_name"] = sup.name if sup else ""

    adj_list = []
    for a in adjustments:
        item = a.as_dict()
        reason = (a.reason or "").lower()
        if reason in ("work_order", "wo") and a.reference_id:
            item["reference_name"] = f"WO #{a.reference_id}"
            item["reference_url"] = f"#/workorders/{a.reference_id}"
        elif reason in ("purchase", "purchase_order", "po") and a.reference_id:
            po = db.purchase_order[a.reference_id]
            po_num = po.po_number if po else f"PO #{a.reference_id}"
            item["reference_name"] = po_num
            item["reference_url"] = f"#/purchasing/{a.reference_id}"
        adj_list.append(item)

    return dict(part=part, adjustments=adj_list)


@action("api/parts/<part_id:int>", method=["PUT"])
@action.uses(db, session, auth)
def parts_update(part_id):
    if not db.part[part_id]:
        raise HTTP(404)
    data = request.json or {}
    db(db.part.id == part_id).update(
        **{k: data[k] for k in data if k in db.part.fields and k != "id"}
    )
    return dict(ok=True)


@action("api/parts/<part_id:int>/adjust", method=["POST"])
@action.uses(db, session, auth)
def parts_adjust(part_id):
    row = db.part[part_id]
    if not row:
        raise HTTP(404)
    data = request.json or {}
    ctx = StockAdjustmentContext(db, row)
    return ctx.execute(
        delta=int(data.get("delta", 0)),
        reason=data.get("reason", "count"),
        reference_id=data.get("reference_id"),
    )


@action("api/parts/<part_id:int>/receive", method=["POST"])
@action.uses(db, session, auth)
def parts_receive(part_id):
    row = db.part[part_id]
    if not row:
        raise HTTP(404)
    data = request.json or {}
    ctx = ReceiveStockContext(db, row)
    return ctx.execute(
        quantity=int(data.get("quantity", 0)),
        reference_id=data.get("reference_id"),
    )
