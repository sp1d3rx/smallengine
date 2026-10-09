"""Retail POS API endpoints — HTTP adapter delegating to Sales DCI Contexts."""
from py4web import action, request, HTTP
from ..common import db, auth, session, require_user
from ..contexts.sales import (
    CreateRetailSaleContext,
    GetRetailSaleContext,
    AddRetailLineContext,
    RemoveRetailLineContext,
    PayRetailSaleContext,
    VoidRetailSaleContext,
    ReturnRetailSaleContext,
)
from ..gantrika.context import NotFoundError, BusinessRuleError


# ── Create draft sale ──────────────────────────────────────────────────────────
@action("api/retail", method=["POST"])
@action.uses(db, session, auth)
def retail_create():
    require_user()
    ctx = CreateRetailSaleContext(db)
    return ctx.execute()


# ── Get sale + lines ───────────────────────────────────────────────────────────
@action("api/retail/<sale_id:int>", method=["GET"])
@action.uses(db, session, auth)
def retail_get(sale_id):
    require_user()
    ctx = GetRetailSaleContext(db)
    try:
        return ctx.execute(sale_id)
    except NotFoundError:
        raise HTTP(404)


# ── Add line item ──────────────────────────────────────────────────────────────
@action("api/retail/<sale_id:int>/lines", method=["POST"])
@action.uses(db, session, auth)
def retail_add_line(sale_id):
    require_user()
    data = request.json or {}
    part_id = data.get("part_id")
    if not part_id:
        raise HTTP(422, '{"error":"part_id required"}')

    quantity = int(data.get("quantity", 1))
    ctx = AddRetailLineContext(db)
    try:
        return ctx.execute(sale_id, int(part_id), quantity)
    except NotFoundError:
        raise HTTP(404)
    except BusinessRuleError as e:
        raise HTTP(422, f'{{"error":"{str(e)}"}}')


# ── Remove line item ───────────────────────────────────────────────────────────
@action("api/retail/<sale_id:int>/lines/<line_id:int>", method=["DELETE"])
@action.uses(db, session, auth)
def retail_remove_line(sale_id, line_id):
    require_user()
    ctx = RemoveRetailLineContext(db)
    try:
        return ctx.execute(sale_id, line_id)
    except (NotFoundError, BusinessRuleError) as e:
        raise HTTP(422, f'{{"error":"{str(e)}"}}')


# ── Pay / finalize ─────────────────────────────────────────────────────────────
@action("api/retail/<sale_id:int>/pay", method=["POST"])
@action.uses(db, session, auth)
def retail_pay(sale_id):
    require_user()
    data = request.json or {}
    ctx = PayRetailSaleContext(db)
    try:
        ctx.execute(
            sale_id=sale_id,
            payment_method=data.get("payment_method", "cash"),
            customer_id=data.get("customer_id") or None,
            cash_customer_name=data.get("cash_customer_name") or "",
            payment_reference=data.get("payment_reference") or "",
        )
        return GetRetailSaleContext(db).execute(sale_id)
    except NotFoundError:
        raise HTTP(404)
    except BusinessRuleError as e:
        raise HTTP(422, f'{{"error":"{str(e)}"}}')


# ── Void ───────────────────────────────────────────────────────────────────────
@action("api/retail/<sale_id:int>/void", method=["POST"])
@action.uses(db, session, auth)
def retail_void(sale_id):
    require_user()
    ctx = VoidRetailSaleContext(db)
    try:
        return ctx.execute(sale_id)
    except NotFoundError:
        raise HTTP(404)


# ── Return items ───────────────────────────────────────────────────────────────
@action("api/retail/<sale_id:int>/return", method=["POST"])
@action.uses(db, session, auth)
def retail_return(sale_id):
    require_user()
    data = request.json or {}
    items = data.get("items", [])
    if not items:
        raise HTTP(422, '{"error":"No items specified"}')

    ctx = ReturnRetailSaleContext(db)
    try:
        return ctx.execute(sale_id, items)
    except NotFoundError:
        raise HTTP(404)
    except BusinessRuleError as e:
        raise HTTP(422, f'{{"error":"{str(e)}"}}')


# ── Part search for POS ────────────────────────────────────────────────────────
@action("api/retail/parts", method=["GET"])
@action.uses(db, session, auth)
def retail_parts_search():
    require_user()
    q = request.query.get("q", "").strip()
    query = (db.part.active == True)
    if q:
        query &= (db.part.description.contains(q) | db.part.part_number.contains(q))
    rows = db(query).select(
        db.part.id, db.part.description, db.part.part_number,
        db.part.price, db.part.qty_on_hand,
        orderby=db.part.description,
        limitby=(0, 20),
    )
    return dict(parts=[r.as_dict() for r in rows])
