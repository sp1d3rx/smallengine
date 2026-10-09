"""
Reports API endpoints.
"""
import collections
import datetime
from py4web import action, HTTP
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


# ── Revenue Report (Cash Basis Valuation) ──────────────────────────────────────

@action("api/reports/revenue", method=["GET"])
@action.uses(db, session, auth)
def report_revenue():
    require_user()
    from ..contexts.accounting import AccountingContext
    ctx = AccountingContext(db)
    return dict(revenue=ctx.calculate_revenue_summary())


@action("api/reports/revenue/<month>", method=["GET"])
@action.uses(db, session, auth)
def report_revenue_detail(month):
    require_user()
    try:
        parts = month.split("-")
        year = int(parts[0])
        m_num = int(parts[1])
        start_date = datetime.date(year, m_num, 1)
        if m_num == 12:
            end_date = datetime.date(year + 1, 1, 1)
        else:
            end_date = datetime.date(year, m_num + 1, 1)
    except Exception:
        raise HTTP(400, "Invalid month format. Expected YYYY-MM.")

    # 1. Closed & paid WOs in range
    all_wos = db((db.work_order.status == "closed") & (db.invoice.status == "paid")).select(
        db.work_order.id, db.work_order.work_type, db.customer.first_name, db.customer.last_name,
        db.invoice.id,
        left=[
            db.customer.on(db.work_order.customer_id == db.customer.id),
            db.invoice.on(db.invoice.work_order_id == db.work_order.id)
        ]
    )
    wos = []
    for r in all_wos:
        invoice_id = r.invoice.id if r.invoice else None
        if not invoice_id:
            continue
        ref_date = _get_paid_in_full_date(db, invoice_id)
        if ref_date and start_date <= ref_date < end_date:
            wos.append((r, ref_date))

    # 2. Paid Sales in range
    all_sales = db(db.sale.status == "paid").select(
        db.sale.id, db.sale.sale_date, db.sale.equipment_id, db.sale.cash_customer_name,
        db.sale.sale_price, db.sale.trade_in_value,
        db.customer.first_name, db.customer.last_name,
        left=db.customer.on(db.sale.customer_id == db.customer.id)
    )
    sales = []
    for r in all_sales:
        ref_date = r.sale.sale_date
        if ref_date and start_date <= ref_date < end_date:
            sales.append(r)

    details = []

    for r, ref_d in wos:
        wo = r.work_order
        from ..roles.base import cast
        from ..roles.work_order_roles import BillableWorkRole
        wo_cast = cast(wo, BillableWorkRole, table_name="work_order")
        labor = float(wo_cast.labor_total(db))
        parts_total = float(wo_cast.parts_total(db) - wo_cast.warranty_parts_total(db))

        # Calculate parts cost
        parts_cost = 0.0
        p_lines = db((db.work_order_part.work_order_id == wo.id) & (db.work_order_part.is_warranty == False)).select(
            db.work_order_part.unit_cost, db.work_order_part.quantity
        )
        for line in p_lines:
            parts_cost += float(line.unit_cost or 0.0) * int(line.quantity or 0)

        cust = f"{r.customer.first_name or ''} {r.customer.last_name or ''}".strip() or "Unknown"
        rev = labor + parts_total

        details.append({
            "date": str(ref_d)[:10],
            "type": f"Work Order #{wo.id}",
            "description": f"{wo.work_type.capitalize()} for {cust}",
            "revenue": float(rev),
            "cogs": float(parts_cost),
            "gross_profit": float(rev - parts_cost)
        })

    for r in sales:
        s = r.sale
        cust = f"{r.customer.first_name or ''} {r.customer.last_name or ''}".strip()
        if not cust:
            cust = s.cash_customer_name or "Walk-in"

        if s.equipment_id:
            rev = float(s.sale_price or 0.0) - float(s.trade_in_value or 0.0)
            equip = db.equipment[s.equipment_id]
            cost = float(equip.acquisition_cost or 0.0) if equip else 0.0

            details.append({
                "date": str(s.sale_date),
                "type": f"Equipment Sale #{s.id}",
                "description": f"Sold equipment to {cust}",
                "revenue": float(rev),
                "cogs": float(cost),
                "gross_profit": float(rev - cost)
            })
        else:
            rev = db(db.sale_line.sale_id == s.id).select(
                db.sale_line.total.sum()
            ).first()[db.sale_line.total.sum()] or 0.0
            rev = float(rev)

            # Parts cost
            cost = 0.0
            lines = db(db.sale_line.sale_id == s.id).select(db.sale_line.unit_cost, db.sale_line.quantity)
            for line in lines:
                cost += float(line.unit_cost or 0.0) * int(line.quantity or 0)

            details.append({
                "date": str(s.sale_date),
                "type": f"Retail POS #{s.id}",
                "description": f"Parts purchased by {cust}",
                "revenue": float(rev),
                "cogs": float(cost),
                "gross_profit": float(rev - cost)
            })

    details.sort(key=lambda x: x["date"], reverse=True)
    return dict(details=details)


# ── Technicians Report ────────────────────────────────────────────────────────

@action("api/reports/technicians", method=["GET"])
@action.uses(db, session, auth)
def report_technicians():
    require_user()
    rows = db(db.work_order.status == "closed").select(
        db.work_order.id, db.work_order.employee_id,
        db.employee.first_name, db.employee.last_name,
        left=db.employee.on(db.work_order.employee_id == db.employee.id)
    )

    techs_data = {}
    for r in rows:
        emp_id = r.work_order.employee_id or 0
        if emp_id not in techs_data:
            name = f"{r.employee.first_name or 'Unassigned'} {r.employee.last_name or ''}".strip()
            techs_data[emp_id] = {
                "id": emp_id,
                "name": name,
                "completed": 0,
                "hours": 0.0,
                "revenue": 0.0,
            }

        techs_data[emp_id]["completed"] += 1

        labor_lines = db(db.work_order_labor.work_order_id == r.work_order.id).select(
            db.work_order_labor.hours, db.work_order_labor.total
        )
        for line in labor_lines:
            techs_data[emp_id]["hours"] += float(line.hours or 0.0)
            techs_data[emp_id]["revenue"] += float(line.total or 0.0)

    return dict(technicians=list(techs_data.values()))


@action("api/reports/technicians/<emp_id:int>", method=["GET"])
@action.uses(db, session, auth)
def report_technician_detail(emp_id):
    require_user()
    wos = db((db.work_order.status == "closed") & (db.work_order.employee_id == emp_id)).select(
        db.work_order.id, db.work_order.date_out, db.work_order.reported_problem,
        db.customer.first_name, db.customer.last_name,
        db.equipment.make, db.equipment.model,
        left=[
            db.customer.on(db.work_order.customer_id == db.customer.id),
            db.equipment.on(db.work_order.equipment_id == db.equipment.id),
        ],
        orderby=~db.work_order.date_out,
    )

    details = []
    for r in wos:
        labor_lines = db(db.work_order_labor.work_order_id == r.work_order.id).select(
            db.work_order_labor.hours, db.work_order_labor.total
        )
        hours = sum(float(l.hours or 0) for l in labor_lines)
        revenue = sum(float(l.total or 0) for l in labor_lines)

        details.append({
            "id": r.work_order.id,
            "date": str(r.work_order.date_out),
            "customer_name": f"{r.customer.first_name or ''} {r.customer.last_name or ''}".strip(),
            "equip_desc": f"{r.equipment.make or ''} {r.equipment.model or ''}".strip(),
            "problem": r.work_order.reported_problem,
            "hours": hours,
            "revenue": revenue
        })
    return dict(details=details)


# ── Warranty Report ───────────────────────────────────────────────────────────

@action("api/reports/warranty", method=["GET"])
@action.uses(db, session, auth)
def report_warranty():
    require_user()
    mfrs = db(db.manufacturer.id > 0).select()
    result = []
    for m in mfrs:
        claims = db(db.warranty_claim.manufacturer_id == m.id).select()
        submitted_count = len(claims)
        paid_count = sum(1 for c in claims if c.status == "paid")

        total_submitted = sum(float((c.covered_labor or 0) + (c.covered_parts or 0)) for c in claims)
        total_paid = sum(float(c.reimbursement_amount or 0) for c in claims if c.status == "paid")

        result.append({
            "id": m.id,
            "name": m.name,
            "submitted_count": submitted_count,
            "paid_count": paid_count,
            "total_submitted": total_submitted,
            "total_paid": total_paid
        })
    return dict(warranty=result)


@action("api/reports/warranty/<mfr_id:int>", method=["GET"])
@action.uses(db, session, auth)
def report_warranty_detail(mfr_id):
    require_user()
    claims = db(db.warranty_claim.manufacturer_id == mfr_id).select(
        db.warranty_claim.ALL,
        db.work_order.id,
        db.customer.first_name, db.customer.last_name,
        db.equipment.make, db.equipment.model,
        left=[
            db.work_order.on(db.warranty_claim.work_order_id == db.work_order.id),
            db.customer.on(db.work_order.customer_id == db.customer.id),
            db.equipment.on(db.work_order.equipment_id == db.equipment.id),
        ],
        orderby=~db.warranty_claim.submitted_date,
    )

    details = []
    for r in claims:
        c = r.warranty_claim
        claimed_total = float((c.covered_labor or 0) + (c.covered_parts or 0))
        details.append({
            "id": c.id,
            "work_order_id": c.work_order_id,
            "mfr_claim_number": c.mfr_claim_number or "—",
            "customer_name": f"{r.customer.first_name or ''} {r.customer.last_name or ''}".strip(),
            "equip_desc": f"{r.equipment.make or ''} {r.equipment.model or ''}".strip(),
            "submitted_date": str(c.submitted_date),
            "status": c.status,
            "covered_labor": float(c.covered_labor or 0),
            "covered_parts": float(c.covered_parts or 0),
            "total_claimed": claimed_total,
            "reimbursement_amount": float(c.reimbursement_amount or 0) if c.status == "paid" else None,
            "payment_date": str(c.payment_date) if c.payment_date else None
        })
    return dict(details=details)


# ── Inventory Report ──────────────────────────────────────────────────────────

@action("api/reports/inventory", method=["GET"])
@action.uses(db, session, auth)
def report_inventory():
    require_user()
    parts = db(db.part.active == True).select(db.part.qty_on_hand, db.part.cost, db.part.price)

    total_qty = 0
    total_cost_val = 0.0
    total_retail_val = 0.0

    for p in parts:
        qty = p.qty_on_hand or 0
        total_qty += qty
        total_cost_val += qty * float(p.cost or 0.0)
        total_retail_val += qty * float(p.price or 0.0)

    # Load grouped categories data as well
    categories_dict = collections.defaultdict(lambda: {"qty": 0, "cost": 0.0, "price": 0.0, "count": 0})
    all_parts = db(db.part.active == True).select()

    for p in all_parts:
        compat_str = p.compatible_categories or "other"
        cats = [c.strip() for c in compat_str.split(",") if c.strip()]
        if not cats:
            cats = ["other"]

        qty = p.qty_on_hand or 0
        c_val = qty * float(p.cost or 0.0)
        p_val = qty * float(p.price or 0.0)

        for cat in cats:
            categories_dict[cat]["count"] += 1
            categories_dict[cat]["qty"] += qty
            categories_dict[cat]["cost"] += c_val
            categories_dict[cat]["price"] += p_val

    categories_list = []
    for cat, d in categories_dict.items():
        margin = d["price"] - d["cost"]
        categories_list.append({
            "category": cat.capitalize(),
            "category_val": cat,
            "count": d["count"],
            "qty": d["qty"],
            "cost": f"{float(d['cost']):,.2f}",
            "price": f"{float(d['price']):,.2f}",
            "margin": f"{float(margin):,.2f}",
            "markup_pct": f"{(margin / d['cost']) * 100:.1f}" if d["cost"] > 0 else "0.0"
        })

    return dict(
        inventory={
            "total_items": len(parts),
            "total_qty": total_qty,
            "total_cost_value": total_cost_val,
            "total_retail_value": total_retail_val,
            "potential_margin": total_retail_val - total_cost_val,
            "categories": categories_list
        }
    )


@action("api/reports/inventory/category/<cat_name>", method=["GET"])
@action.uses(db, session, auth)
def report_inventory_category_detail(cat_name):
    require_user()
    if cat_name == "other":
        parts = db(
            (db.part.active == True) &
            ((db.part.compatible_categories == "") | (db.part.compatible_categories == None))
        ).select()
    else:
        parts = db((db.part.active == True) & (db.part.compatible_categories.contains(cat_name))).select()

    details = []
    for p in parts:
        qty = p.qty_on_hand or 0
        c_val = qty * float(p.cost or 0.0)
        p_val = qty * float(p.price or 0.0)
        details.append({
            "part_number": p.part_number,
            "description": p.description,
            "qty_on_hand": qty,
            "cost": f"{float(p.cost or 0):.2f}",
            "price": f"{float(p.price or 0):.2f}",
            "total_cost_val": f"{c_val:.2f}",
            "total_price_val": f"{p_val:.2f}",
            "margin": f"{(p_val - c_val):.2f}"
        })
    return dict(parts=details)
