"""
Purchase order API endpoints.
"""
import datetime
from decimal import Decimal
from py4web import action, request, HTTP
from ..common import db, auth, session, require_admin as require_user
from ..contexts.purchasing import (
    CreatePOContext, UpdatePOContext, ReceivePOLinesContext, CancelPOContext,
    AddPOLineContext, DeletePOLineContext,
)


@action("api/purchaseorders", method=["GET"])
@action.uses(db, session, auth)
def po_list():
    require_user()
    status = request.query.get("status", "").strip()
    query = db.purchase_order.id > 0
    if status:
        if "," in status:
            query &= db.purchase_order.status.belongs(status.split(","))
        else:
            query &= db.purchase_order.status == status
    rows = db(query).select(
        db.purchase_order.ALL,
        db.supplier.name, db.supplier.phone,
        left=db.supplier.on(db.purchase_order.supplier_id == db.supplier.id),
        orderby=~db.purchase_order.created_on,
    )
    result = []
    for row in rows:
        item = row.purchase_order.as_dict()
        item["supplier_name"] = row.supplier.name or ""
        result.append(item)
    return dict(purchase_orders=result)


@action("api/purchaseorders", method=["POST"])
@action.uses(db, session, auth)
def po_create():
    require_user()
    data = request.json or {}
    supplier = db.supplier[data.get("supplier_id")]
    if not supplier:
        raise HTTP(422, '{"error":"supplier_id required"}')
    lines = data.get("lines", [])
    expected_by = None
    if data.get("expected_by"):
        expected_by = datetime.date.fromisoformat(data["expected_by"])
    ctx = CreatePOContext(db, supplier)
    result = ctx.execute(
        lines=lines,
        shipping_method=data.get("shipping_method"),
        expected_by=expected_by,
        notes=data.get("notes", ""),
        po_number=data.get("po_number"),
    )
    db.commit()
    return result


@action("api/purchaseorders/<po_id:int>", method=["GET"])
@action.uses(db, session, auth)
def po_get(po_id):
    require_user()
    po = db.purchase_order[po_id]
    if not po:
        raise HTTP(404)
    supplier = db.supplier[po.supplier_id]
    contacts = db(
        (db.supplier_contact.supplier_id == po.supplier_id)
        & (db.supplier_contact.is_primary == True)
    ).select().first()
    lines = db(db.purchase_order_line.po_id == po_id).select(
        orderby=db.purchase_order_line.id
    )
    line_list = []
    for line in lines:
        item = line.as_dict()
        if line.part_id:
            part = db.part[line.part_id]
            item["part_number"] = part.part_number if part else ""
        else:
            item["part_number"] = ""
        line_list.append(item)
    return dict(
        purchase_order=po.as_dict(),
        supplier=supplier.as_dict() if supplier else {},
        primary_contact=contacts.as_dict() if contacts else None,
        lines=line_list,
    )


@action("api/purchaseorders/<po_id:int>", method=["PUT"])
@action.uses(db, session, auth)
def po_update(po_id):
    require_user()
    po = db.purchase_order[po_id]
    if not po:
        raise HTTP(404)
    if po.status in ("received", "cancelled"):
        raise HTTP(422, '{"error":"Cannot edit a received or cancelled PO"}')
    data = request.json or {}
    if data.get("expected_by"):
        data["expected_by"] = datetime.date.fromisoformat(data["expected_by"])
    ctx = UpdatePOContext(db, po)
    ctx.execute(**data)
    db.commit()
    return dict(ok=True)


@action("api/purchaseorders/<po_id:int>/receive", method=["POST"])
@action.uses(db, session, auth)
def po_receive(po_id):
    require_user()
    po = db.purchase_order[po_id]
    if not po:
        raise HTTP(404)
    data = request.json or {}
    receipts = data.get("receipts", [])
    ctx = ReceivePOLinesContext(db, po)
    result = ctx.execute(receipts)
    db.commit()
    return result


@action("api/purchaseorders/<po_id:int>/cancel", method=["POST"])
@action.uses(db, session, auth)
def po_cancel(po_id):
    require_user()
    po = db.purchase_order[po_id]
    if not po:
        raise HTTP(404)
    ctx = CancelPOContext(db, po)
    result = ctx.execute()
    db.commit()
    return result


# ── PO line management (add/remove while in draft) ───────────────────────────

@action("api/purchaseorders/<po_id:int>/lines", method=["POST"])
@action.uses(db, session, auth)
def po_add_line(po_id):
    require_user()
    po = db.purchase_order[po_id]
    if not po:
        raise HTTP(404)
    data = request.json or {}
    ctx = AddPOLineContext(db, po)
    try:
        return ctx.execute(
            qty_ordered=int(data.get("qty_ordered", 1)),
            unit_cost=Decimal(str(data.get("unit_cost", "0"))),
            part_id=data.get("part_id"),
            description=data.get("description", ""),
        )
    except Exception as e:
        raise HTTP(422, f'{{"error":"{str(e)}"}}')


@action("api/purchaseorders/<po_id:int>/lines/<line_id:int>", method=["DELETE"])
@action.uses(db, session, auth)
def po_delete_line(po_id, line_id):
    require_user()
    po = db.purchase_order[po_id]
    if not po:
        raise HTTP(404)
    ctx = DeletePOLineContext(db, po)
    try:
        return ctx.execute(line_id)
    except Exception as e:
        raise HTTP(422, f'{{"error":"{str(e)}"}}')
