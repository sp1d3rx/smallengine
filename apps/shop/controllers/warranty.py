"""
Warranty claim and manufacturer API endpoints.
"""
from decimal import Decimal
from py4web import action, request, HTTP
from ..common import db, auth, session, require_user, require_admin
from ..contexts.warranty import OpenWarrantyClaimContext, RecordWarrantyPaymentContext


# ── Manufacturers ─────────────────────────────────────────────────────────────

@action("api/manufacturers", method=["GET"])
@action.uses(db, session, auth)
def manufacturers_list():
    require_user()
    rows = db(db.manufacturer.id > 0).select(orderby=db.manufacturer.name)
    return dict(manufacturers=[r.as_dict() for r in rows])


@action("api/manufacturers", method=["POST"])
@action.uses(db, session, auth)
def manufacturers_create():
    require_admin()
    data = request.json or {}
    result = db.manufacturer.validate_and_insert(**{
        k: data.get(k) for k in [
            "name", "contact_name", "phone", "email", "dealer_id",
            "warranty_notes", "flat_rate_labor",
        ]
    })
    if result.get("errors"):
        raise HTTP(422, str(result["errors"]))
    db.commit()
    return dict(id=result["id"])


@action("api/manufacturers/<mfr_id:int>", method=["GET"])
@action.uses(db, session, auth)
def manufacturers_get(mfr_id):
    require_user()
    row = db.manufacturer[mfr_id]
    if not row:
        raise HTTP(404)
    return dict(manufacturer=row.as_dict())


@action("api/manufacturers/<mfr_id:int>", method=["PUT"])
@action.uses(db, session, auth)
def manufacturers_update(mfr_id):
    require_admin()
    row = db.manufacturer[mfr_id]
    if not row:
        raise HTTP(404)
    data = request.json or {}
    allowed = [
        "name", "contact_name", "phone", "email", "dealer_id",
        "warranty_notes", "flat_rate_labor",
    ]
    db(db.manufacturer.id == mfr_id).update(**{k: data[k] for k in allowed if k in data})
    db.commit()
    return dict(ok=True)


# ── Warranty Claims ───────────────────────────────────────────────────────────

@action("api/warranty", method=["GET"])
@action.uses(db, session, auth)
def warranty_list():
    require_user()
    status = request.query.get("status")
    mfr_id = request.query.get("manufacturer_id")
    query = db.warranty_claim.id > 0
    if status:
        query &= db.warranty_claim.status == status
    if mfr_id:
        query &= db.warranty_claim.manufacturer_id == int(mfr_id)

    rows = db(query).select(
        db.warranty_claim.ALL,
        db.manufacturer.name,
        db.work_order.id,
        db.customer.first_name, db.customer.last_name,
        db.equipment.make, db.equipment.model,
        left=[
            db.manufacturer.on(db.warranty_claim.manufacturer_id == db.manufacturer.id),
            db.work_order.on(db.warranty_claim.work_order_id == db.work_order.id),
            db.customer.on(db.work_order.customer_id == db.customer.id),
            db.equipment.on(db.work_order.equipment_id == db.equipment.id),
        ],
        orderby=~db.warranty_claim.submitted_date,
    )

    claims = []
    for r in rows:
        d = r.warranty_claim.as_dict()
        d["manufacturer_name"] = r.manufacturer.name or "Unknown Manufacturer"
        d["customer_name"] = f"{r.customer.first_name or ''} {r.customer.last_name or ''}".strip() or "Unknown Customer"
        d["equip_desc"] = f"{r.equipment.make or ''} {r.equipment.model or ''}".strip() or "Unknown Equipment"
        claims.append(d)
    return dict(claims=claims)


@action("api/warranty/eligible_workorders", method=["GET"])
@action.uses(db, session, auth)
def eligible_workorders():
    require_user()
    # Find closed work orders with is_warranty = True that do not have a warranty_claim yet
    claims_subquery = db()._select(db.warranty_claim.work_order_id)
    query = (
        (db.work_order.is_warranty == True) &
        (db.work_order.status == "closed") &
        (~db.work_order.id.belongs(claims_subquery))
    )
    rows = db(query).select(
        db.work_order.id, db.work_order.date_in, db.work_order.manufacturer_id,
        db.customer.first_name, db.customer.last_name,
        db.equipment.make, db.equipment.model,
        left=[
            db.customer.on(db.work_order.customer_id == db.customer.id),
            db.equipment.on(db.work_order.equipment_id == db.equipment.id),
        ],
    )
    res = []
    for r in rows:
        from ..roles.base import cast
        from ..roles.work_order_roles import BillableWorkRole
        wo_cast = cast(r.work_order, BillableWorkRole, table_name="work_order")
        labor_total = wo_cast.warranty_labor_total(db)
        parts_total = wo_cast.warranty_parts_total(db)

        res.append({
            "id": r.work_order.id,
            "date_in": str(r.work_order.date_in),
            "manufacturer_id": r.work_order.manufacturer_id,
            "customer_name": f"{r.customer.first_name or ''} {r.customer.last_name or ''}".strip(),
            "equip_desc": f"{r.equipment.make or ''} {r.equipment.model or ''}".strip(),
            "covered_labor": float(labor_total),
            "covered_parts": float(parts_total),
        })
    return dict(work_orders=res)


def _safe_decimal(val, default="0"):
    if val is None or val == "":
        return Decimal(default) if default is not None else None
    try:
        return Decimal(str(val))
    except Exception:
        return Decimal(default) if default is not None else None


@action("api/warranty", method=["POST"])
@action.uses(db, session, auth)
def warranty_create():
    require_user()
    data = request.json or {}
    wo = db.work_order[data.get("work_order_id")]
    mfr = db.manufacturer[data.get("manufacturer_id")]
    if not wo or not mfr:
        raise HTTP(422, "work_order_id and manufacturer_id required")
    ctx = OpenWarrantyClaimContext(db, wo, mfr)
    claim_id = ctx.execute(
        covered_labor=_safe_decimal(data.get("covered_labor"), "0"),
        covered_parts=_safe_decimal(data.get("covered_parts"), "0"),
        mfr_claim_number=data.get("mfr_claim_number"),
    )
    return dict(id=claim_id)


@action("api/warranty/<claim_id:int>", method=["GET"])
@action.uses(db, session, auth)
def warranty_get(claim_id):
    require_user()
    row = db.warranty_claim[claim_id]
    if not row:
        raise HTTP(404)
    mfr = db.manufacturer[row.manufacturer_id]
    wo = db.work_order[row.work_order_id]
    cust = db.customer[wo.customer_id] if wo else None
    equip = db.equipment[wo.equipment_id] if wo else None

    d = row.as_dict()
    d["manufacturer_name"] = mfr.name if mfr else "Unknown Manufacturer"
    d["customer_name"] = f"{cust.first_name} {cust.last_name}" if cust else "Unknown Customer"
    d["equip_desc"] = f"{equip.make} {equip.model}" if equip else "Unknown Equipment"
    return dict(claim=d)


@action("api/warranty/<claim_id:int>/payment", method=["POST"])
@action.uses(db, session, auth)
def warranty_record_payment(claim_id):
    require_user()
    claim = db.warranty_claim[claim_id]
    if not claim:
        raise HTTP(404)
    data = request.json or {}
    ctx = RecordWarrantyPaymentContext(db, claim)
    res = ctx.execute(
        amount=_safe_decimal(data.get("amount"), "0"),
    )
    return res
