"""
Work order API endpoints.
"""

import datetime
from decimal import Decimal
from py4web import action, request, HTTP
from ..common import db, auth, session, require_user
from ..contexts.repair import (
    RepairIntakeContext,
    DiagnoseRepairContext,
    RecordApprovalContext,
    CancelRepairContext,
    NeedPartsContext,
    PartsArrivedContext,
    AddLaborContext,
    AddPartContext,
    GenerateInvoiceContext,
    CloseRepairContext,
    NotifyReadyContext,
)


# ── List + create ─────────────────────────────────────────────────────────────


@action("api/workorders", method=["GET"])
@action.uses(db, session, auth)
def work_orders_list():
    require_user()
    status = request.query.get("status")
    employee_id = request.query.get("employee_id")
    view = request.query.get("view")
    limit = request.query.get("limit")
    offset = request.query.get("offset")
    desc = request.query.get("desc") == "1"

    limitby = None
    if limit:
        try:
            off = int(offset or 0)
            limitby = (off, off + int(limit))
        except (TypeError, ValueError):
            limitby = None

    if view == "dashboard":
        # Dashboard only needs open WOs plus closed-but-not-yet-picked-up units.
        # Bounding here keeps the landing page from loading the full work-order history.
        open_statuses = [
            "intake",
            "diagnosed",
            "awaiting_approval",
            "awaiting_parts",
            "in_repair",
            "ready",
        ]
        query = (db.work_order.status.belongs(open_statuses)) | (
            (db.work_order.status == "closed") & (db.work_order.date_out == None)
        )
    else:
        query = db.work_order.id > 0
        if status:
            if "," in status:
                query &= db.work_order.status.belongs(status.split(","))
            else:
                query &= db.work_order.status == status
        if employee_id:
            query &= db.work_order.employee_id == int(employee_id)

    rows = db(query).select(
        db.work_order.ALL,
        db.customer.first_name,
        db.customer.last_name,
        db.customer.phone,
        db.customer.email,
        db.customer.contact_preference,
        db.equipment.make,
        db.equipment.model,
        db.equipment.category,
        db.employee.first_name,
        db.employee.last_name,
        left=[
            db.customer.on(db.work_order.customer_id == db.customer.id),
            db.equipment.on(db.work_order.equipment_id == db.equipment.id),
            db.employee.on(db.work_order.employee_id == db.employee.id),
        ],
        orderby=(
            ~db.work_order.date_promised | ~db.work_order.date_in
            if desc
            else db.work_order.date_promised | db.work_order.date_in
        ),
        limitby=limitby,
    )
    result = []
    for row in rows:
        item = row.work_order.as_dict()
        item["customer"] = {
            "first_name": row.customer.first_name,
            "last_name": row.customer.last_name,
            "phone": row.customer.phone,
            "email": row.customer.email,
            "contact_preference": row.customer.contact_preference,
        }
        item["equipment"] = {
            "make": row.equipment.make,
            "model": row.equipment.model,
            "category": row.equipment.category,
        }
        item["employee"] = (
            {
                "first_name": row.employee.first_name,
                "last_name": row.employee.last_name,
            }
            if row.employee.first_name
            else None
        )
        result.append(item)
    return dict(work_orders=result)


@action("api/workorders", method=["POST"])
@action.uses(db, session, auth)
def work_orders_create():
    require_user()
    data = request.json or {}
    customer = db.customer[data.get("customer_id")]
    equipment = db.equipment[data.get("equipment_id")]
    if not customer:
        raise HTTP(422, '{"error":"customer_id required"}')
    if not equipment:
        raise HTTP(422, '{"error":"equipment_id required"}')

    date_promised = None
    if data.get("date_promised"):
        from datetime import date

        date_promised = date.fromisoformat(data["date_promised"])

    ctx = RepairIntakeContext(db, customer, equipment)
    wo_id = ctx.execute(
        reported_problem=data.get("reported_problem", ""),
        work_type=data.get("work_type", "repair"),
        employee_id=data.get("employee_id"),
        date_promised=date_promised,
        notes=data.get("notes", ""),
        pre_approved_limit=_safe_decimal(data.get("pre_approved_limit"), default=None),
        estimated_cost=_safe_decimal(data.get("estimated_cost"), default=None),
    )
    db.commit()
    return dict(id=wo_id)


# ── Promise date suggestion ───────────────────────────────────────────────────


@action("api/promise-date", method=["GET"])
@action.uses(db, session, auth)
def promise_date():
    require_user()
    work_type = request.query.get("work_type", "repair")
    from ..contexts.repair import RepairIntakeContext

    # Use a throwaway context just for the calculation (no rows needed)
    from ..roles.base import RoleObject
    import types

    ctx = object.__new__(RepairIntakeContext)
    ctx.db = db
    suggested = ctx.calculate_promise_date(work_type)
    return dict(date=str(suggested))


# ── Single work order ─────────────────────────────────────────────────────────


@action("api/workorders/<wo_id:int>", method=["GET"])
@action.uses(db, session, auth)
def work_orders_get(wo_id):
    require_user()
    wo = db.work_order[wo_id]
    if not wo:
        raise HTTP(404)

    customer = db.customer[wo.customer_id]
    equipment = db.equipment[wo.equipment_id]
    employee = db.employee[wo.employee_id] if wo.employee_id else None

    labor = db(db.work_order_labor.work_order_id == wo_id).select(
        orderby=db.work_order_labor.created_on
    )
    parts = db(db.work_order_part.work_order_id == wo_id).select(
        orderby=db.work_order_part.created_on
    )
    comms = db(db.work_order_communication.work_order_id == wo_id).select(
        db.work_order_communication.ALL,
        db.employee.first_name,
        db.employee.last_name,
        left=db.employee.on(db.work_order_communication.employee_id == db.employee.id),
        orderby=~db.work_order_communication.logged_at,
    )

    # Equipment history (other WOs for this equipment, most recent first)
    history = db(
        (db.work_order.equipment_id == wo.equipment_id) & (db.work_order.id != wo_id)
    ).select(
        db.work_order.id,
        db.work_order.work_type,
        db.work_order.status,
        db.work_order.reported_problem,
        db.work_order.date_in,
        db.work_order.date_out,
        orderby=~db.work_order.date_in,
        limitby=(0, 10),
    )

    # Suggested parts for this equipment category
    suggested_parts = []
    if equipment and equipment.category:
        suggested_parts = db(
            (db.part.active == True)
            & (db.part.qty_on_hand > 0)
            & (db.part.compatible_categories.contains(equipment.category))
        ).select(orderby=db.part.description)

    comm_list = []
    for comm in comms:
        item = comm.work_order_communication.as_dict()
        item["employee_name"] = (
            f"{comm.employee.first_name} {comm.employee.last_name}"
            if comm.employee.first_name
            else "—"
        )
        comm_list.append(item)

    invoice = db(db.invoice.work_order_id == wo_id).select().first()
    payments = []
    if invoice:
        payments = db(db.payment.invoice_id == invoice.id).select(
            orderby=db.payment.received_on
        )

    shop = db(db.shop_settings).select().first()
    default_threshold = (
        float(shop.estimate_approval_threshold)
        if shop and shop.estimate_approval_threshold
        else 100.0
    )
    approval_threshold = (
        float(wo.pre_approved_limit)
        if wo.pre_approved_limit is not None
        else default_threshold
    )

    return dict(
        work_order=wo.as_dict(),
        customer=customer.as_dict() if customer else {},
        equipment=equipment.as_dict() if equipment else {},
        employee=employee.as_dict() if employee else None,
        labor=[r.as_dict() for r in labor],
        parts=[r.as_dict() for r in parts],
        communications=comm_list,
        history=[r.as_dict() for r in history],
        suggested_parts=[r.as_dict() for r in suggested_parts],
        invoice=invoice.as_dict() if invoice else None,
        payments=[p.as_dict() for p in payments],
        approval_threshold=approval_threshold,
    )


def _safe_decimal(val, default="0"):
    if val is None or val == "":
        return Decimal(default) if default is not None else None
    try:
        return Decimal(str(val))
    except Exception:
        return Decimal(default) if default is not None else None


def _safe_int(val, default=None):
    if val is None or val == "":
        return default
    try:
        return int(val)
    except Exception:
        return default


# ── Status actions ────────────────────────────────────────────────────────────


@action("api/workorders/<wo_id:int>/status", method=["POST"])
@action.uses(db, session, auth)
def work_orders_advance_status(wo_id):
    require_user()
    wo = db.work_order[wo_id]
    if not wo:
        raise HTTP(404)
    data = request.json or {}
    action_name = data.get("action", "advance")

    if action_name == "advance":
        from ..roles.base import cast
        from ..roles.work_order_roles import ProgressableRole

        wo_role = cast(wo, ProgressableRole, table_name="work_order")
        new_status = wo_role.advance(db)
        result = {"status": new_status}
    elif action_name == "diagnose":
        ctx = DiagnoseRepairContext(db, wo)
        result = ctx.execute(
            diagnosis=data.get("diagnosis", ""),
            estimated_cost=_safe_decimal(data.get("estimated_cost"), "0"),
        )
    elif action_name == "approve":
        ctx = RecordApprovalContext(db, wo)
        result = ctx.execute(
            approved=data.get("approved", True),
            decline_reason=data.get("decline_reason", "customer_declined"),
            decline_detail=data.get("decline_detail", ""),
        )
    elif action_name == "cancel":
        ctx = CancelRepairContext(db, wo)
        result = ctx.execute(
            reason=data.get("reason", "other"),
            detail=data.get("detail", ""),
        )
    elif action_name == "need_parts":
        ctx = NeedPartsContext(db, wo)
        result = ctx.execute()
    elif action_name == "parts_arrived":
        ctx = PartsArrivedContext(db, wo)
        result = ctx.execute()
    elif action_name == "close":
        ctx = CloseRepairContext(db, wo)
        result = ctx.execute()
    elif action_name == "notify_ready":
        from datetime import date

        pickup_date = (
            date.fromisoformat(data["pickup_date"]) if data.get("pickup_date") else None
        )
        ctx = NotifyReadyContext(db, wo)
        result = ctx.execute(pickup_date=pickup_date)
    elif action_name == "generate_invoice":
        ctx = GenerateInvoiceContext(db, wo)
        result = ctx.execute()
    elif action_name == "record_payment":
        invoice = db(db.invoice.work_order_id == wo_id).select().first()
        if not invoice:
            raise HTTP(422, '{"error":"Generate invoice before recording payment"}')
        amount = float(data.get("amount") or invoice.total)
        method = data.get("method", "cash")
        db.payment.insert(
            invoice_id=invoice.id,
            amount=amount,
            method=method,
            reference=data.get("reference", ""),
            received_on=datetime.date.today(),
        )
        paid_row = (
            db(db.payment.invoice_id == invoice.id)
            .select(db.payment.amount.sum())
            .first()
        )
        total_paid = float(paid_row[db.payment.amount.sum()] or 0)
        new_inv_status = "paid" if total_paid >= float(invoice.total) else "partial"
        db(db.invoice.id == invoice.id).update(status=new_inv_status)
        result = {"ok": True, "invoice_status": new_inv_status}
    elif action_name == "mark_pickup":
        from datetime import date

        pickup_str = data.get("pickup_date")
        pickup_date = date.fromisoformat(pickup_str) if pickup_str else date.today()
        db.work_order[wo_id] = dict(date_out=pickup_date)
        result = {"ok": True, "date_out": str(pickup_date)}
    elif action_name == "transfer_to_inventory":
        db.equipment[wo.equipment_id] = dict(
            condition="renewed_inventory", customer_id=None
        )
        result = {"ok": True}
    else:
        raise HTTP(400, f'{{"error":"Unknown action: {action_name}"}}')

    db.commit()
    return result


# ── Labor lines ───────────────────────────────────────────────────────────────


@action("api/workorders/<wo_id:int>/labor", method=["POST"])
@action.uses(db, session, auth)
def work_orders_add_labor(wo_id):
    require_user()
    wo = db.work_order[wo_id]
    if not wo:
        raise HTTP(404)
    if wo.status in ("closed", "cancelled"):
        raise HTTP(422, '{"error":"Cannot modify a closed or cancelled work order"}')
    data = request.json or {}
    ctx = AddLaborContext(db, wo)
    try:
        line_id = ctx.execute(
            description=data.get("description", ""),
            hours=_safe_decimal(data.get("hours"), "0"),
            rate=_safe_decimal(data.get("rate"), default=None),
            employee_id=_safe_int(data.get("employee_id"), default=None),
            is_warranty=bool(data.get("is_warranty", False)),
        )
        return dict(id=line_id)
    except Exception as e:
        raise HTTP(422, f'{{"error":"{str(e)}"}}')


@action("api/workorders/<wo_id:int>/labor/<line_id:int>", method=["PUT"])
@action.uses(db, session, auth)
def work_orders_update_labor(wo_id, line_id):
    require_user()
    data = request.json or {}
    row = (
        db(
            (db.work_order_labor.id == line_id)
            & (db.work_order_labor.work_order_id == wo_id)
        )
        .select()
        .first()
    )
    if not row:
        raise HTTP(404)
    if "hours" in data or "rate" in data:
        hours = _safe_decimal(data.get("hours"), str(row.hours))
        rate = _safe_decimal(data.get("rate"), str(row.rate))
        data["total"] = float(hours * rate)
    db(
        (db.work_order_labor.id == line_id)
        & (db.work_order_labor.work_order_id == wo_id)
    ).update(
        **{
            k: data[k]
            for k in [
                "description",
                "hours",
                "rate",
                "total",
                "is_warranty",
                "employee_id",
            ]
            if k in data
        }
    )
    db.commit()
    return dict(ok=True)


@action("api/workorders/<wo_id:int>/labor/<line_id:int>", method=["DELETE"])
@action.uses(db, session, auth)
def work_orders_delete_labor(wo_id, line_id):
    require_user()
    wo = db.work_order[wo_id]
    if wo and wo.status in ("closed", "cancelled"):
        raise HTTP(422, '{"error":"Cannot modify a closed or cancelled work order"}')
    db(
        (db.work_order_labor.id == line_id)
        & (db.work_order_labor.work_order_id == wo_id)
    ).delete()
    db.commit()
    return dict(ok=True)


# ── Parts lines ───────────────────────────────────────────────────────────────


@action("api/workorders/<wo_id:int>/parts", method=["POST"])
@action.uses(db, session, auth)
def work_orders_add_part(wo_id):
    require_user()
    wo = db.work_order[wo_id]
    if not wo:
        raise HTTP(404)
    if wo.status in ("closed", "cancelled"):
        raise HTTP(422, '{"error":"Cannot modify a closed or cancelled work order"}')
    data = request.json or {}
    ctx = AddPartContext(db, wo)
    try:
        line_id = ctx.execute(
            quantity=_safe_int(data.get("quantity"), default=1),
            unit_price=_safe_decimal(data.get("unit_price"), "0"),
            part_id=_safe_int(data.get("part_id"), default=None),
            description=data.get("description"),
            unit_cost=_safe_decimal(data.get("unit_cost"), default=None),
            is_warranty=bool(data.get("is_warranty", False)),
        )
        return dict(id=line_id)
    except Exception as e:
        raise HTTP(422, f'{{"error":"{str(e)}"}}')


@action("api/workorders/<wo_id:int>/parts/<line_id:int>", method=["DELETE"])
@action.uses(db, session, auth)
def work_orders_delete_part(wo_id, line_id):
    require_user()
    from ..roles.base import cast
    from ..roles.parts_roles import StockableRole

    wo = db.work_order[wo_id]
    if wo and wo.status in ("closed", "cancelled"):
        raise HTTP(422, '{"error":"Cannot modify a closed or cancelled work order"}')
    line = (
        db(
            (db.work_order_part.id == line_id)
            & (db.work_order_part.work_order_id == wo_id)
        )
        .select()
        .first()
    )
    if line and line.part_id:
        part_row = db.part[line.part_id]
        if part_row:
            stockable = cast(part_row, StockableRole, table_name="part")
            stockable.adjust_stock(db, line.quantity, "work_order_removal", wo_id)
    db(
        (db.work_order_part.id == line_id) & (db.work_order_part.work_order_id == wo_id)
    ).delete()
    db.commit()
    return dict(ok=True)


# ── Communication log ─────────────────────────────────────────────────────────


@action("api/workorders/<wo_id:int>/communications", method=["GET"])
@action.uses(db, session, auth)
def communications_list(wo_id):
    require_user()
    if not db.work_order[wo_id]:
        raise HTTP(404)
    rows = db(db.work_order_communication.work_order_id == wo_id).select(
        db.work_order_communication.ALL,
        db.employee.first_name,
        db.employee.last_name,
        left=db.employee.on(db.work_order_communication.employee_id == db.employee.id),
        orderby=~db.work_order_communication.logged_at,
    )
    result = []
    for row in rows:
        item = row.work_order_communication.as_dict()
        item["employee_name"] = (
            f"{row.employee.first_name} {row.employee.last_name}"
            if row.employee.first_name
            else "—"
        )
        result.append(item)
    return dict(communications=result)


@action("api/workorders/<wo_id:int>/communications", method=["POST"])
@action.uses(db, session, auth)
def communications_create(wo_id):
    require_user()
    if not db.work_order[wo_id]:
        raise HTTP(404)
    data = request.json or {}
    if not data.get("summary", "").strip():
        raise HTTP(422, '{"error":"summary required"}')
    comm_id = db.work_order_communication.insert(
        work_order_id=wo_id,
        employee_id=data.get("employee_id"),
        logged_at=datetime.datetime.utcnow(),
        method=data.get("method", "call"),
        direction=data.get("direction", "outbound"),
        summary=data["summary"].strip(),
    )
    db.commit()
    return dict(id=comm_id)


# ── Invoice detail ─────────────────────────────────────────────────────────────


@action("api/workorders/<wo_id:int>/invoice", method=["GET"])
@action.uses(db, session, auth)
def work_order_invoice_detail(wo_id):
    require_user()
    wo = db.work_order[wo_id]
    if not wo:
        raise HTTP(404)
    invoice = db(db.invoice.work_order_id == wo_id).select().first()
    if not invoice:
        raise HTTP(404, '{"error":"No invoice for this work order"}')
    labor = db(db.work_order_labor.work_order_id == wo_id).select(
        orderby=db.work_order_labor.created_on
    )
    parts = db(db.work_order_part.work_order_id == wo_id).select(
        orderby=db.work_order_part.created_on
    )
    payments = db(db.payment.invoice_id == invoice.id).select(
        orderby=db.payment.received_on
    )
    customer = db.customer[wo.customer_id]
    equipment = db.equipment[wo.equipment_id]
    settings = db(db.shop_settings.id > 0).select().first()
    return dict(
        invoice=invoice.as_dict(),
        work_order=wo.as_dict(),
        customer=customer.as_dict() if customer else {},
        equipment=equipment.as_dict() if equipment else {},
        labor=[r.as_dict() for r in labor],
        parts=[r.as_dict() for r in parts],
        payments=[p.as_dict() for p in payments],
        shop=settings.as_dict() if settings else {},
    )


# ── Intake Document (printable authorization & agreement) ─────────────────────


@action("api/workorders/<wo_id:int>/intake-doc", method=["GET"])
@action.uses(db, session, auth)
def work_order_intake_doc(wo_id):
    require_user()
    wo = db.work_order[wo_id]
    if not wo:
        raise HTTP(404)
    customer = db.customer[wo.customer_id]
    equipment = db.equipment[wo.equipment_id]
    employee = db.employee[wo.employee_id] if wo.employee_id else None
    settings = db(db.shop_settings.id > 0).select().first()
    return dict(
        work_order=wo.as_dict(),
        customer=customer.as_dict() if customer else {},
        equipment=equipment.as_dict() if equipment else {},
        employee=employee.as_dict() if employee else None,
        shop=settings.as_dict() if settings else {},
    )
