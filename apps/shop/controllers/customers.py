"""
Customer API endpoints — thin controllers that parse requests and call contexts/queries.
"""
import datetime
from py4web import action, request, HTTP
from ..common import db, auth, session, require_user


# ── Helper for Cash Basis paid-in-full date ───────────────────────────────────

def _get_paid_in_full_date(db, invoice_id):
    """Find the latest payment date for an invoice. Fallback to invoice modified_on/created_on."""
    latest_payment = db(db.payment.invoice_id == invoice_id).select(
        db.payment.received_on, orderby=~db.payment.received_on
    ).first()
    if latest_payment and latest_payment.received_on:
        return latest_payment.received_on

    invoice = db.invoice[invoice_id]
    if invoice:
        ref_datetime = invoice.modified_on or invoice.created_on
        if ref_datetime:
            return ref_datetime.date()
    return None


@action("api/customers", method=["GET"])
@action.uses(db, session, auth)
def customers_list():
    require_user()
    query_str = request.query.get("q", "").strip()
    query = db.customer.id > 0
    if query_str:
        query &= (
            db.customer.first_name.contains(query_str)
            | db.customer.last_name.contains(query_str)
            | db.customer.phone.contains(query_str)
            | db.customer.email.contains(query_str)
        )
    rows = db(query).select(orderby=db.customer.last_name | db.customer.first_name, limitby=(0, 50))
    return dict(customers=[r.as_dict() for r in rows])


@action("api/customers/retention", method=["GET"])
@action.uses(db, session, auth)
def customers_retention():
    require_user()
    customers = db(db.customer.id > 0).select(
        db.customer.id, db.customer.first_name, db.customer.last_name, db.customer.phone, db.customer.email
    )

    result = []
    today = datetime.date.today()

    for c in customers:
        invoices = db((db.invoice.customer_id == c.id) & (db.invoice.status == "paid")).select(
            db.invoice.id, db.invoice.total
        )
        sales = db((db.sale.customer_id == c.id) & (db.sale.status == "paid")).select(
            db.sale.id, db.sale.total, db.sale.sale_date
        )

        total_spent = 0.0
        visit_dates = []
        visit_count = 0

        for inv in invoices:
            total_spent += float(inv.total or 0.0)
            visit_count += 1
            p_date = _get_paid_in_full_date(db, inv.id)
            if p_date:
                visit_dates.append(p_date)

        for s in sales:
            total_spent += float(s.total or 0.0)
            visit_count += 1
            if s.sale_date:
                visit_dates.append(s.sale_date)

        last_visit = None
        days_since = 9999
        status = "No visits"

        if visit_dates:
            last_visit = max(visit_dates)
            days_since = (today - last_visit).days
            if days_since <= 90:
                status = "Active"
            elif days_since <= 180:
                status = "Lapsing"
            else:
                status = "Inactive"

        # CRM Contact Logs (Interaction check)
        latest_contact = db(db.customer_contact_log.customer_id == c.id).select(
            db.customer_contact_log.contact_date, orderby=~db.customer_contact_log.contact_date
        ).first()
        last_contact_date = str(latest_contact.contact_date) if latest_contact else "Never"

        avg_ticket = (total_spent / visit_count) if visit_count > 0 else 0.0

        result.append({
            "id": c.id,
            "name": f"{c.first_name or ''} {c.last_name or ''}".strip(),
            "phone": c.phone or "—",
            "email": c.email or "—",
            "total_spent": float(total_spent),
            "visit_count": int(visit_count),
            "avg_ticket": float(avg_ticket),
            "last_visit": str(last_visit) if last_visit else "Never",
            "last_contact": last_contact_date,
            "days_since": int(days_since),
            "status": status
        })

    result.sort(key=lambda x: x["total_spent"], reverse=True)
    return dict(customers=result)


@action("api/customers", method=["POST"])
@action.uses(db, session, auth)
def customers_create():
    require_user()
    data = request.json or {}
    allowed = ["first_name", "last_name", "phone", "email", "contact_preference",
               "address", "city", "state", "zip_code", "customer_type", "notes"]
    payload = {k: data[k] for k in allowed if k in data}
    result = db.customer.insert(**payload)
    db.commit()
    return dict(id=result["id"])


@action("api/customers/<customer_id:int>", method=["GET"])
@action.uses(db, session, auth)
def customers_get(customer_id):
    require_user()
    row = db.customer[customer_id]
    if not row:
        raise HTTP(404)
    equipment = db(db.equipment.customer_id == customer_id).select(
        orderby=db.equipment.make | db.equipment.model
    )
    work_orders = db(db.work_order.customer_id == customer_id).select(
        db.work_order.id, db.work_order.work_type, db.work_order.status,
        db.work_order.reported_problem, db.work_order.date_in, db.work_order.date_promised,
        db.equipment.make, db.equipment.model, db.equipment.category,
        left=db.equipment.on(db.work_order.equipment_id == db.equipment.id),
        orderby=~db.work_order.date_in,
        limitby=(0, 30),
    )
    retail_sales = db(
        (db.sale.customer_id == customer_id) &
        (db.sale.status != "open")
    ).select(orderby=~db.sale.sale_date, limitby=(0, 20))

    # Retrieve customer contact logs
    contact_logs = db(db.customer_contact_log.customer_id == customer_id).select(
        db.customer_contact_log.id, db.customer_contact_log.contact_date,
        db.customer_contact_log.contact_type, db.customer_contact_log.notes,
        db.employee.first_name, db.employee.last_name,
        left=db.employee.on(db.customer_contact_log.employee_id == db.employee.id),
        orderby=~db.customer_contact_log.contact_date | ~db.customer_contact_log.id
    )

    return dict(
        customer=row.as_dict(),
        equipment=[e.as_dict() for e in equipment],
        work_orders=[r.as_dict() for r in work_orders],
        retail_sales=[r.as_dict() for r in retail_sales],
        contact_logs=[{
            "id": r.customer_contact_log.id,
            "contact_date": str(r.customer_contact_log.contact_date),
            "contact_type": r.customer_contact_log.contact_type,
            "notes": r.customer_contact_log.notes,
            "logged_by": f"{r.employee.first_name or ''} {r.employee.last_name or ''}".strip() or "System"
        } for r in contact_logs],
    )


@action("api/customers/<customer_id:int>", method=["PUT"])
@action.uses(db, session, auth)
def customers_update(customer_id):
    require_user()
    if not db.customer[customer_id]:
        raise HTTP(404)
    data = request.json or {}
    allowed = [
        "first_name", "last_name", "phone", "email", "contact_preference",
        "address", "city", "state", "zip_code", "customer_type", "notes"
    ]
    db(db.customer.id == customer_id).update(**{k: data[k] for k in allowed if k in data})
    db.commit()
    return dict(ok=True)


@action("api/customers/<customer_id:int>/equipment", method=["POST"])
@action.uses(db, session, auth)
def equipment_create(customer_id):
    require_user()
    if not db.customer[customer_id]:
        raise HTTP(404)
    data = request.json or {}
    allowed = ["category", "make", "model", "serial_number", "year", "notes"]
    payload = {k: data[k] for k in allowed if k in data}
    payload["customer_id"] = customer_id
    payload["condition"] = "customer_owned"
    result = db.equipment.insert(**payload)
    db.commit()
    return dict(id=result["id"])


@action("api/customers/<customer_id:int>/equipment/<equipment_id:int>", method=["PUT"])
@action.uses(db, session, auth)
def equipment_update(customer_id, equipment_id):
    require_user()
    row = db.equipment[equipment_id]
    if not row or row.customer_id != customer_id:
        raise HTTP(404)
    data = request.json or {}
    allowed = ["category", "make", "model", "serial_number", "year", "notes"]
    db(db.equipment.id == equipment_id).update(**{k: data[k] for k in allowed if k in data})
    db.commit()
    return dict(ok=True)


@action("api/customers/<customer_id:int>/equipment/<equipment_id:int>", method=["DELETE"])
@action.uses(db, session, auth)
def equipment_delete(customer_id, equipment_id):
    require_user()
    row = db.equipment[equipment_id]
    if not row or row.customer_id != customer_id:
        raise HTTP(404)
    # Refuse deletion if linked to any work order
    if db(db.work_order.equipment_id == equipment_id).count():
        raise HTTP(409, '{"error":"Equipment has work order history"}')
    db(db.equipment.id == equipment_id).delete()
    db.commit()
    return dict(ok=True)


@action("api/customers/<customer_id:int>/contacts", method=["POST"])
@action.uses(db, session, auth)
def add_customer_contact(customer_id):
    require_user()
    if not db.customer[customer_id]:
        raise HTTP(404)
    data = request.json or {}

    # Resolve current employee/user logging it
    user_id = auth.current_user.get("id") if auth.current_user else None
    employee = db(db.employee.auth_user_id == user_id).select().first() if user_id else None
    employee_id = employee.id if employee else None

    contact_date = data.get("contact_date")
    if contact_date:
        contact_date = datetime.date.fromisoformat(contact_date)
    else:
        contact_date = datetime.date.today()

    db.customer_contact_log.insert(
        customer_id=customer_id,
        employee_id=employee_id,
        contact_date=contact_date,
        contact_type=data.get("contact_type", "call"),
        notes=data.get("notes", "").strip()
    )
    db.commit()
    return dict(ok=True)
