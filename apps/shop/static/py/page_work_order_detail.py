"""Work order detail — tech bench view, sub-card binders, and action workflows."""
from datetime import date
from browser import document, window

import api
import app
from gantrika import (
    currency,
    form_data,
    local_time,
    safe_action,
    short_date,
)
from constants import WO_STATUS_LABELS as STATUS_LABELS

CANCEL_REASONS = [
    ("customer_declined", "Customer declined repair"),
    ("customer_unresponsive", "Customer unresponsive"),
    ("not_worth_repairing", "Not worth repairing"),
    ("picked_up_as_is", "Picked up as-is"),
    ("other", "Other"),
]


# ── View Model Projectors (Pure Functions) ─────────────────────────────────────

def _project_labor_line(line):
    return {
        "id": line["id"],
        "description": line.get("description", ""),
        "hours": line.get("hours", 0),
        "rate_fmt": currency(line.get("rate")),
        "total_fmt": currency(line.get("total")),
        "is_warranty": bool(line.get("is_warranty")),
    }


def _project_part_line(line):
    return {
        "id": line["id"],
        "description": line.get("description", ""),
        "quantity": line.get("quantity", 1),
        "unit_price_fmt": currency(line.get("unit_price")),
        "total_fmt": currency(line.get("total")),
        "is_warranty": bool(line.get("is_warranty")),
    }


def _project_comm_entry(comm):
    return {
        "logged_at": local_time(comm.get("logged_at")),
        "direction_arrow": "→" if comm.get("direction") == "outbound" else "←",
        "method_title": comm.get("method", "").title(),
        "employee_name": comm.get("employee_name", ""),
        "summary": comm.get("summary", ""),
    }


def _project_history_item(hw):
    hw_wo = hw.get("work_order") or hw
    hist_status = hw_wo.get("status", "")
    return {
        "id": hw_wo.get("id"),
        "status": hist_status,
        "status_label": STATUS_LABELS.get(hist_status, hist_status),
        "reported_problem_short": hw_wo.get("reported_problem", "")[:50],
        "date_in": hw_wo.get("date_in", ""),
    }


def _project_suggested_part(part):
    return {
        "id": part["id"],
        "description": part.get("description", ""),
        "qty_on_hand": part.get("qty_on_hand", 0),
        "price": part.get("price", 0),
        "cost": part.get("cost", 0),
    }


def _running_total_ctx(labor_total, parts_total, grand_total, estimated_cost, approval_threshold):
    ctx = {
        "labor_total_fmt": currency(labor_total),
        "parts_total_fmt": currency(parts_total),
        "grand_total_fmt": currency(grand_total),
        "has_overage": False,
        "overage_fmt": "",
        "overage_color": "",
    }
    if estimated_cost and grand_total > estimated_cost:
        overage = grand_total - estimated_cost
        ctx["has_overage"] = True
        ctx["overage_fmt"] = f"+{currency(overage)} over estimate"
        ctx["overage_color"] = "#dc2626" if grand_total > approval_threshold else "#ea580c"
    elif grand_total > approval_threshold:
        ctx["has_overage"] = True
        ctx["overage_fmt"] = f"Exceeds {currency(approval_threshold)} approval limit"
        ctx["overage_color"] = "#dc2626"
    return ctx


def _project_work_order_vm(wo_id, data):
    """Transform raw API response into a presentation view-model."""
    wo = data.get("work_order", {})
    cust = data.get("customer", {})
    equip = data.get("equipment", {})
    employee = data.get("employee")
    invoice = data.get("invoice")

    status = wo.get("status", "")
    status_label = STATUS_LABELS.get(status, status)

    contact_pref = cust.get("contact_preference", "call")
    pref_labels = {"call": "Call:", "sms": "SMS:", "email": "Email:"}
    contact_label = "Email:" if contact_pref == "email" else pref_labels.get(contact_pref, "Call:")
    contact_value = cust.get("email") if contact_pref == "email" else cust.get("phone", "")

    tech_name = f"{employee['first_name']} {employee['last_name']}" if employee else "Unassigned"
    year = equip.get("year") or ""
    equip_desc = f"{year} {equip.get('make', '')} {equip.get('model', '')}".strip()
    estimated_cost = wo.get("estimated_cost")
    is_open = status not in ("closed", "cancelled")

    labor_lines = [_project_labor_line(l) for l in data.get("labor", [])]
    part_lines = [_project_part_line(p) for p in data.get("parts", [])]
    comms_data = [_project_comm_entry(c) for c in data.get("communications", [])]
    history_data = [_project_history_item(h) for h in data.get("history", [])]
    sugg_data = [_project_suggested_part(s) for s in data.get("suggested_parts", [])]

    labor_total = sum(l.get("total", 0) for l in data.get("labor", []))
    parts_total = sum(p.get("total", 0) for p in data.get("parts", []))
    grand_total = labor_total + parts_total
    rt_ctx = _running_total_ctx(
        labor_total, parts_total, grand_total,
        estimated_cost, data.get("approval_threshold", 100.0)
    )

    date_out = wo.get("date_out") or ""
    is_picked_up = bool(date_out)
    days_waiting = 0
    show_inventory_option = False
    if status == "closed" and not is_picked_up:
        try:
            ref_str = str(wo.get("modified_on") or wo.get("date_in") or "")[:10]
            if ref_str:
                days_waiting = (date.today() - date.fromisoformat(ref_str)).days
                show_inventory_option = days_waiting >= 30
        except Exception:
            pass

    return {
        "wo_id": wo_id,
        "status": status,
        "status_label": status_label,
        "equip_desc": equip_desc,
        "equip_sn": equip.get("serial_number") or "—",
        "equip_category": equip.get("category", "").replace("_", " ").title(),
        "tech_name": tech_name,
        "date_in": wo.get("date_in", ""),
        "date_promised": wo.get("date_promised", ""),
        "work_type": wo.get("work_type", "").title(),
        "reported_problem": wo.get("reported_problem", ""),
        "has_diagnosis": bool(wo.get("diagnosis")),
        "diagnosis": wo.get("diagnosis", ""),
        "has_estimated_cost": bool(estimated_cost),
        "estimated_cost_fmt": currency(estimated_cost),
        "cust_id": cust.get("id"),
        "cust_name": f"{cust.get('first_name', '')} {cust.get('last_name', '')}",
        "contact_label": contact_label,
        "contact_value": contact_value,
        "comms": comms_data,
        "history": history_data,
        "has_notes": bool(wo.get("notes")),
        "notes": wo.get("notes", ""),
        "is_open": is_open,
        "labor_lines": labor_lines,
        "part_lines": part_lines,
        "suggested_parts": sugg_data,
        **rt_ctx,
        "has_invoice": bool(invoice),
        "inv_id": invoice["id"] if invoice else None,
        "inv_total_fmt": currency(invoice.get("total")) if invoice else "",
        "inv_status": invoice.get("status", "draft") if invoice else "",
        "inv_is_paid": bool(invoice and invoice.get("status") == "paid"),
        "is_notified": bool(wo.get("customer_notified_at")),
        "notified_at": local_time(wo.get("customer_notified_at")),
        "is_picked_up": is_picked_up,
        "date_out": str(date_out),
        "days_waiting": days_waiting,
        "show_inventory_option": show_inventory_option,
    }


# ── Public Entry Point ─────────────────────────────────────────────────────────

def render_detail(wo_id):
    """Render the full work order tech bench view."""
    try:
        data = api.get_work_order(wo_id)
    except api.ApiError as err:
        app.toast(f"Error loading WO: {err.message}", "error")
        return

    vm = _project_work_order_vm(wo_id, data)
    app.render("tpl-wo-detail", vm)
    _bind_bench_events(wo_id, data)


# ── Bench Event Binders ────────────────────────────────────────────────────────

def _bind_bench_events(wo_id, data):
    """Attach event handlers for the bench workspace."""
    btn_labor = document.getElementById("btn-add-labor")
    if btn_labor:
        btn_labor.bind("click", lambda evt: _show_labor_form(wo_id, data))

    btn_part = document.getElementById("btn-add-part")
    if btn_part:
        btn_part.bind("click", lambda evt: _show_part_form(wo_id))

    btn_comm = document.getElementById("btn-log-comm")
    if btn_comm:
        btn_comm.bind("click", lambda evt: _show_comm_form(wo_id, data))

    window.deleteLabor = lambda wi, li: _delete_labor(wi, li)
    window.deletePart = lambda wi, li: _delete_part(wi, li)

    _bind_suggested_btns(wo_id)
    _bind_action_buttons(wo_id, data.get("work_order", {}))


def _bind_suggested_btns(wo_id):
    """Bind Add buttons on suggested parts."""
    for btn in document.select(".btn-add-suggested"):
        card = btn.closest(".suggested-part")
        if not card:
            continue
        part_id = card.getAttribute("data-part-id")
        price = float(card.getAttribute("data-price") or 0)
        cost = float(card.getAttribute("data-cost") or 0)
        if part_id:
            @safe_action("Part added", on_success=lambda _: _reload_parts_card(wo_id))
            def _add(evt, pid=int(part_id), pr=price, co=cost):
                api.add_part(wo_id, {
                    "part_id": pid, "quantity": 1,
                    "unit_price": pr, "unit_cost": co,
                })
            btn.bind("click", _add)


def _bind_action_buttons(wo_id, wo):
    """Bind lifecycle transition buttons in the right action rail."""
    def _action(action_name, **kwargs):
        try:
            api.advance_work_order(wo_id, action_name, **kwargs)
            app.toast("Updated", "success")
            render_detail(wo_id)
        except api.ApiError as err:
            app.toast(f"Error: {err.message}", "error")

    btn_maps = [
        ("btn-action-diagnose", lambda evt: _show_diagnosis_form(wo_id)),
        ("btn-action-cancel", lambda evt: _show_cancel_form(wo_id)),
        ("btn-action-request-approval", lambda evt: _action("diagnose",
            diagnosis=wo.get("diagnosis") or "", estimated_cost=wo.get("estimated_cost") or 0)),
        ("btn-action-start-repair", lambda evt: _action("diagnose",
            diagnosis=wo.get("diagnosis") or "", estimated_cost=0)),
        ("btn-action-approve", lambda evt: _action("approve", approved=True)),
        ("btn-action-decline", lambda evt: _show_cancel_form(wo_id, is_decline=True)),
        ("btn-action-notify", lambda evt: _action("notify_ready")),
        ("btn-action-ready", lambda evt: _action("advance")),
        ("btn-action-need-parts", lambda evt: _action("need_parts")),
        ("btn-action-parts-arrived", lambda evt: _action("parts_arrived")),
        ("btn-action-close", lambda evt: _action("close")),
        ("btn-action-pickup", lambda evt: _show_pickup_form(wo_id)),
        ("btn-action-payment", lambda evt: _show_payment_form(wo_id)),
    ]

    for btn_id, handler in btn_maps:
        btn = document.getElementById(btn_id)
        if btn:
            btn.bind("click", handler)

    btn_inv = document.getElementById("btn-action-to-inventory")
    if btn_inv:
        def _to_inv(evt):
            if window.confirm("Move this unit to shop inventory? Customer link will be removed."):
                _action("transfer_to_inventory")
        btn_inv.bind("click", _to_inv)

    btn_invoice = document.getElementById("btn-action-invoice")
    if btn_invoice:
        @safe_action("Invoice generated", on_success=lambda _: render_detail(wo_id))
        def _gen_inv(evt):
            api.advance_work_order(wo_id, "generate_invoice")
        btn_invoice.bind("click", _gen_inv)


# ── Partial Card Reloaders ────────────────────────────────────────────────────

def _reload_labor_card(wo_id):
    """Refresh labor lines and running total without full page re-render."""
    try:
        data = api.get_work_order(wo_id)
    except api.ApiError:
        return
    labor_data = [_project_labor_line(l) for l in data.get("labor", [])]
    is_open = data.get("work_order", {}).get("status", "") not in ("closed", "cancelled")

    labor_div = document.getElementById("labor-lines")
    if labor_div:
        labor_div.html = app.render_partial("tpl-wo-labor-lines", {
            "wo_id": wo_id, "is_open": is_open, "labor_lines": labor_data,
        })
    form_div = document.getElementById("labor-form")
    if form_div:
        form_div.html = ""

    _update_running_totals(data)


def _reload_parts_card(wo_id):
    """Refresh parts lines, suggested parts, and running total."""
    try:
        data = api.get_work_order(wo_id)
    except api.ApiError:
        return
    parts_data = [_project_part_line(p) for p in data.get("parts", [])]
    sugg_data = [_project_suggested_part(s) for s in data.get("suggested_parts", [])]
    is_open = data.get("work_order", {}).get("status", "") not in ("closed", "cancelled")

    part_lines_div = document.getElementById("part-lines")
    if part_lines_div:
        part_lines_div.html = app.render_partial("tpl-wo-part-lines", {
            "wo_id": wo_id, "is_open": is_open, "part_lines": parts_data,
        })
    form_div = document.getElementById("part-form")
    if form_div:
        form_div.html = ""

    sugg_div = document.getElementById("suggested-parts")
    if sugg_div:
        sugg_div.html = app.render_partial("tpl-wo-suggested-parts", {
            "is_open": is_open, "suggested_parts": sugg_data,
        })
        _bind_suggested_btns(wo_id)

    _update_running_totals(data)


def _update_running_totals(data):
    """Re-compute and inject running total widget HTML."""
    labor_total = sum(l.get("total", 0) for l in data.get("labor", []))
    parts_total = sum(p.get("total", 0) for p in data.get("parts", []))
    wo = data.get("work_order", {})
    rt_ctx = _running_total_ctx(
        labor_total, parts_total, labor_total + parts_total,
        wo.get("estimated_cost"), data.get("approval_threshold", 100.0)
    )
    total_div = document.getElementById("running-total")
    if total_div:
        total_div.html = app.render_partial("tpl-wo-running-total", rt_ctx)


# ── Modals & Inline Forms ──────────────────────────────────────────────────────

def _show_labor_form(wo_id, data):
    form_div = document.getElementById("labor-form")
    if not form_div:
        return
    employees = []
    try:
        for emp in api.list_employees().get("employees", []):
            employees.append({"id": emp["id"], "name": f"{emp['first_name']} {emp['last_name']}"})
    except api.ApiError:
        pass

    form_div.html = app.render_partial("tpl-wo-labor-form", {"employees": employees})
    form = document.getElementById("form-labor")
    if form:
        @safe_action("Labor added", on_success=lambda _: _reload_labor_card(wo_id))
        def _submit(evt):
            raw = form_data("#form-labor")
            clean = {
                "description": raw.get("description", ""),
                "hours": float(raw.get("hours") or 0),
            }
            if raw.get("rate"):
                clean["rate"] = float(raw["rate"])
            if raw.get("employee_id"):
                clean["employee_id"] = int(raw["employee_id"])
            if raw.get("is_warranty"):
                clean["is_warranty"] = True
            api.add_labor(wo_id, clean)
        form.bind("submit", _submit)

    cancel = document.getElementById("btn-cancel-labor")
    if cancel:
        cancel.bind("click", lambda evt: setattr(form_div, "html", ""))


def _show_part_form(wo_id):
    form_div = document.getElementById("part-form")
    if not form_div:
        return
    form_div.html = app.render_partial("tpl-wo-part-form", {})
    form = document.getElementById("form-part")
    if form:
        @safe_action("Part added", on_success=lambda _: _reload_parts_card(wo_id))
        def _submit(evt):
            raw = form_data("#form-part")
            clean = {
                "description": raw.get("description", ""),
                "quantity": int(raw.get("quantity") or 1),
                "unit_price": float(raw.get("unit_price") or 0),
            }
            if raw.get("unit_cost"):
                clean["unit_cost"] = float(raw["unit_cost"])
            if raw.get("part_id"):
                clean["part_id"] = int(raw["part_id"])
            if raw.get("is_warranty"):
                clean["is_warranty"] = True
            api.add_part(wo_id, clean)
        form.bind("submit", _submit)

    cancel = document.getElementById("btn-cancel-part")
    if cancel:
        cancel.bind("click", lambda evt: setattr(form_div, "html", ""))


def _show_comm_form(wo_id, data):
    cust = data.get("customer", {})
    cust_name = f"{cust.get('first_name', '')} {cust.get('last_name', '')}".strip()
    contact_pref = cust.get("contact_preference", "call")
    phone = cust.get("phone", "")
    email = cust.get("email", "")

    pref_labels = {"call": "phone call", "sms": "SMS", "email": "email", "in_person": "in person"}
    contact_href = f"mailto:{email}" if contact_pref == "email" and email else (f"tel:{phone}" if phone else "")
    contact_display = email if contact_pref == "email" and email else phone

    method_options = [
        {"value": val, "label": lbl, "is_selected": contact_pref == val}
        for val, lbl in [("call", "Phone call"), ("sms", "SMS"), ("email", "Email"), ("in_person", "In person")]
    ]

    employees = [
        {"id": emp["id"], "name": f"{emp['first_name']} {emp['last_name']}"}
        for emp in api.list_employees().get("employees", [])
    ] if api else []

    body_html = app.render_partial("tpl-wo-comm-form", {
        "cust_name": cust_name,
        "contact_href": contact_href,
        "contact_display": contact_display,
        "contact_pref_label": pref_labels.get(contact_pref, contact_pref),
        "methods": method_options,
        "employees": employees,
    })
    app.modal("Contact Customer", body_html)

    form = document.getElementById("form-comm")
    if form:
        @safe_action("Logged", on_success=lambda _: render_detail(wo_id), close_modal=True)
        def _submit(evt):
            data_out = form_data("#form-comm")
            if data_out.get("employee_id"):
                data_out["employee_id"] = int(data_out["employee_id"])
            api.add_communication(wo_id, data_out)
        form.bind("submit", _submit)

    cancel = document.getElementById("btn-cancel-comm")
    if cancel:
        cancel.bind("click", lambda evt: app.close_modal())


def _show_diagnosis_form(wo_id):
    panel = document.getElementById("action-panel")
    if not panel:
        return
    panel.html = app.render_partial("tpl-wo-diagnosis-form", {})
    form = document.getElementById("form-diagnosis")
    if form:
        @safe_action("Diagnosis recorded", on_success=lambda _: render_detail(wo_id))
        def _submit(evt):
            data_out = form_data("#form-diagnosis")
            api.advance_work_order(wo_id, "diagnose",
                diagnosis=data_out.get("diagnosis", ""),
                estimated_cost=float(data_out.get("estimated_cost") or 0))
        form.bind("submit", _submit)

    cancel = document.getElementById("btn-cancel-diag")
    if cancel:
        cancel.bind("click", lambda evt: render_detail(wo_id))


def _show_cancel_form(wo_id, is_decline=False):
    panel = document.getElementById("action-panel")
    if not panel:
        return
    reasons = [
        {"value": val, "label": label, "is_selected": is_decline and val == "customer_declined"}
        for val, label in CANCEL_REASONS
    ]
    title = "Customer Declined" if is_decline else "Cancel Work Order"
    panel.html = app.render_partial("tpl-wo-cancel-form", {"title": title, "reasons": reasons})

    form = document.getElementById("form-cancel")
    if form:
        @safe_action("Work order cancelled", on_success=lambda _: render_detail(wo_id))
        def _submit(evt):
            data_out = form_data("#form-cancel")
            if is_decline:
                api.advance_work_order(wo_id, "approve", approved=False,
                    decline_reason=data_out.get("reason"), decline_detail=data_out.get("detail"))
            else:
                api.advance_work_order(wo_id, "cancel",
                    reason=data_out.get("reason"), detail=data_out.get("detail"))
        form.bind("submit", _submit)

    back_btn = document.getElementById("btn-cancel-cancel")
    if back_btn:
        back_btn.bind("click", lambda evt: render_detail(wo_id))


def _show_pickup_form(wo_id):
    panel = document.getElementById("action-panel")
    if not panel:
        return
    panel.html = app.render_partial("tpl-wo-pickup-form", {"today": str(date.today())})
    form = document.getElementById("form-pickup")
    if form:
        @safe_action("Pickup recorded", on_success=lambda _: render_detail(wo_id))
        def _submit(evt):
            data_out = form_data("#form-pickup")
            pickup_date = data_out.get("pickup_date") or str(date.today())
            api.advance_work_order(wo_id, "mark_pickup", pickup_date=pickup_date)
        form.bind("submit", _submit)

    cancel = document.getElementById("btn-cancel-pickup")
    if cancel:
        cancel.bind("click", lambda evt: render_detail(wo_id))


def _show_payment_form(wo_id):
    panel = document.getElementById("action-panel")
    if not panel:
        return
    panel.html = app.render_partial("tpl-wo-payment-form", {})
    form = document.getElementById("form-payment")
    if form:
        @safe_action("Payment recorded", on_success=lambda _: render_detail(wo_id))
        def _submit(evt):
            data_out = form_data("#form-payment")
            api.advance_work_order(wo_id, "record_payment",
                method=data_out.get("method"),
                amount=float(data_out.get("amount") or 0),
                reference=data_out.get("reference"),
            )
        form.bind("submit", _submit)

    cancel = document.getElementById("btn-cancel-payment")
    if cancel:
        cancel.bind("click", lambda evt: render_detail(wo_id))


# ── Invoice View ──────────────────────────────────────────────────────────────

def render_invoice(wo_id):
    """Render a printable invoice page for a work order."""
    try:
        data = api.get_invoice(wo_id)
    except api.ApiError as err:
        app.toast(f"Error loading invoice: {err.message}", "error")
        return

    inv = data.get("invoice", {})
    wo = data.get("work_order", {})
    cust = data.get("customer", {})
    equip = data.get("equipment", {})
    labor_lines = data.get("labor", [])
    part_lines = data.get("parts", [])
    payments = data.get("payments", [])
    shop = data.get("shop", {})

    shop_addr = shop.get("address", "")
    shop_city = shop.get("city", "")
    shop_state = shop.get("state", "TX")
    shop_zip = shop.get("zip_code", "")
    shop_addr_line = f"{shop_addr}, {shop_city}, {shop_state} {shop_zip}".strip(", ")

    year = equip.get("year") or ""
    equip_desc = f"{year} {equip.get('make', '')} {equip.get('model', '')}".strip()

    labor_data = [{
        "description": line.get("description", ""),
        "hours_fmt": f"{line.get('hours', 0):.2f}",
        "rate_fmt": currency(line.get("rate")),
        "total_fmt": currency(line.get("total")),
        "is_warranty": bool(line.get("is_warranty")),
    } for line in labor_lines]

    parts_data = [{
        "description": line.get("description", ""),
        "quantity": line.get("quantity", 1),
        "unit_price_fmt": currency(line.get("unit_price")),
        "total_fmt": currency(line.get("total")),
        "is_warranty": bool(line.get("is_warranty")),
    } for line in part_lines]

    payments_data = [{
        "received_on": pay.get("received_on", ""),
        "method_label": (pay.get("method") or "").replace("_", " ").title(),
        "reference": pay.get("reference", ""),
        "amount_fmt": currency(pay.get("amount")),
    } for pay in payments]

    subtotal = inv.get("subtotal", 0)
    warranty_labor = sum(l.get("total", 0) for l in labor_lines if l.get("is_warranty"))
    warranty_parts = sum(p.get("total", 0) for p in part_lines if p.get("is_warranty"))
    warranty_credit = warranty_labor + warranty_parts
    non_warranty_parts = sum(p.get("total", 0) for p in part_lines if not p.get("is_warranty"))
    actual_tax = non_warranty_parts * 0.0825
    total_customer = subtotal - warranty_credit + actual_tax
    total_paid = sum(p.get("amount", 0) for p in payments)
    balance_due = max(0.0, total_customer - total_paid)

    app.render("tpl-invoice", {
        "wo_id": wo_id,
        "inv_id": inv.get("id", ""),
        "shop_name": shop.get("shop_name", "Certified Small Engine"),
        "shop_addr_line": shop_addr_line,
        "shop_phone": shop.get("phone", ""),
        "date_in": wo.get("date_in", ""),
        "date_out": wo.get("date_out", "") or "",
        "inv_status": inv.get("status", "draft").title(),
        "cust_name": f"{cust.get('first_name', '')} {cust.get('last_name', '')}".strip(),
        "cust_phone": cust.get("phone") or cust.get("email") or "",
        "equip_desc": equip_desc,
        "equip_sn": equip.get("serial_number") or "",
        "labor_lines": labor_data,
        "part_lines": parts_data,
        "payments": payments_data,
        "subtotal_fmt": currency(subtotal),
        "has_warranty_credit": warranty_credit > 0,
        "warranty_credit_fmt": currency(warranty_credit),
        "tax_rate_pct": "8.25%",
        "tax_fmt": currency(actual_tax),
        "total_fmt": currency(total_customer),
        "total_paid_fmt": currency(total_paid),
        "is_paid": balance_due <= 0.005,
        "balance_due_fmt": currency(balance_due),
    })


def render_intake_doc(wo_id):
    """Render a printable intake document and service authorization agreement."""
    try:
        data = api.get(f"/shop/api/workorders/{wo_id}/intake-doc")
    except api.ApiError as err:
        app.toast(f"Error loading intake document: {err.message}", "error")
        return

    wo = data.get("work_order", {})
    cust = data.get("customer", {})
    equip = data.get("equipment", {})
    employee = data.get("employee")
    shop = data.get("shop", {})

    shop_addr = shop.get("address", "")
    shop_city = shop.get("city", "")
    shop_state = shop.get("state", "TX")
    shop_zip = shop.get("zip_code", "")
    shop_addr_line = f"{shop_addr}, {shop_city}, {shop_state} {shop_zip}".strip(", ")

    cust_addr = cust.get("address", "")
    cust_city = cust.get("city", "")
    cust_state = cust.get("state", "TX")
    cust_zip = cust.get("zip_code", "")
    cust_addr_line = f"{cust_addr}, {cust_city}, {cust_state} {cust_zip}".strip(", ")

    year = equip.get("year") or ""
    equip_desc = f"{year} {equip.get('make', '')} {equip.get('model', '')}".strip()

    tech_name = f"{employee['first_name']} {employee['last_name']}" if employee else "Unassigned"
    pref_labels = {"call": "Phone call", "sms": "SMS text", "email": "Email"}
    contact_pref = pref_labels.get(cust.get("contact_preference"), cust.get("contact_preference", ""))

    threshold = float(wo.get("pre_approved_limit")) if wo.get("pre_approved_limit") is not None else float(shop.get("estimate_approval_threshold") or 100.00)
    disclaimer = shop.get("intake_disclaimer") or (
        "1. Diagnostic Fee & Authorization: I authorize the shop to inspect, diagnose, and test-operate the equipment listed above. "
        "A standard diagnostic evaluation fee applies if the repair estimate is declined.\n\n"
        "2. Approval Threshold: Repairs estimated up to the pre-authorized limit or shop approval threshold will proceed automatically. "
        "Any repairs exceeding this amount require customer approval before completion.\n\n"
        "3. Storage & Abandoned Equipment: Equipment must be picked up within 30 calendar days of completion notification. "
        "Items remaining after 30 days are subject to a $5.00/day storage fee. Equipment left unclaimed after 60 days will be "
        "deemed abandoned and disposed of or sold to recover accrued repair and storage costs in accordance with Texas law.\n\n"
        "4. Limited Warranty & Liability: Service labor is guaranteed for 30 days. Replaced parts carry manufacturer warranties. "
        "The shop assumes no liability for loss or damage caused by fire, theft, accidents, or acts of nature beyond reasonable control."
    )
    disclaimer = disclaimer.replace("${approval_threshold}", currency(threshold))

    app.render("tpl-intake-doc", {
        "wo_id": wo_id,
        "shop_name": shop.get("shop_name", "Certified Small Engine"),
        "shop_addr_line": shop_addr_line,
        "shop_phone": shop.get("phone", ""),
        "shop_email": shop.get("email", ""),
        "date_in": short_date(wo.get("date_in")),
        "date_promised": short_date(wo.get("date_promised")),
        "work_type": wo.get("work_type", "").title(),
        "tech_name": tech_name,
        "cust_name": f"{cust.get('first_name', '')} {cust.get('last_name', '')}".strip(),
        "cust_phone": cust.get("phone", ""),
        "cust_email": cust.get("email", ""),
        "cust_addr_line": cust_addr_line,
        "contact_pref": contact_pref,
        "equip_desc": equip_desc,
        "equip_category": equip.get("category", "").replace("_", " ").title(),
        "equip_sn": equip.get("serial_number") or "—",
        "equip_condition": equip.get("condition", "").replace("_", " ").title(),
        "reported_problem": wo.get("reported_problem", ""),
        "has_notes": bool(wo.get("notes")),
        "notes": wo.get("notes", ""),
        "has_estimate": bool(wo.get("estimated_cost")),
        "estimated_cost_fmt": currency(wo.get("estimated_cost")),
        "approval_threshold_fmt": currency(threshold),
        "intake_disclaimer": disclaimer,
    })


# ── Delete Helpers ────────────────────────────────────────────────────────────

def _delete_labor(wo_id, line_id):
    if not window.confirm("Remove this labor line?"):
        return
    @safe_action("Removed", on_success=lambda _: _reload_labor_card(wo_id))
    def _do():
        api.delete_labor(wo_id, line_id)
    _do()


def _delete_part(wo_id, line_id):
    if not window.confirm("Remove this parts line?"):
        return
    @safe_action("Removed", on_success=lambda _: _reload_parts_card(wo_id))
    def _do():
        api.delete_part(wo_id, line_id)
    _do()
