"""Customers page — split-panel registry and CRM retention dashboards. GET requests run in a web worker."""
import app
import api
import json
import datetime
from gantrika import form_data, currency, human_days_ago, safe_action
from browser import document, window, worker as bworker
from constants import EQUIPMENT_CATEGORIES, WO_STATUS_LABELS as STATUS_LABELS

ACTIVE_STATUSES = {"intake", "diagnosed", "awaiting_approval", "awaiting_parts", "in_repair", "ready"}
BASE = "/shop/api"

_current_customer_id = None
_active_subview = "registry"  # mutable global subview state: "registry" or "retention"

# ── Web worker ─────────────────────────────────────────────────────────────────

_worker = None
_pending = []
_callbacks = {}
_req_id = [0]


def _on_worker_message(ev):
    req_id = str(int(ev.data["req_id"]))
    cb = _callbacks.pop(req_id, None)
    if cb:
        if "error" in ev.data:
            cb(None, str(ev.data["error"]))
        else:
            cb(json.loads(str(ev.data["json"])), None)


def _on_worker_load(w):
    global _worker
    _worker = w
    for send_fn in _pending:
        send_fn()
    _pending.clear()


bworker.create_worker("cust-api-worker", _on_worker_load, _on_worker_message)


def _fetch(url, callback):
    _req_id[0] += 1
    rid = _req_id[0]
    _callbacks[str(rid)] = callback
    msg = {"req_id": rid, "url": window.location.origin + url}
    try:
        _worker.send(msg)
    except AttributeError:
        _pending.append(lambda m=msg: _worker.send(m))


# ── Public entry points ────────────────────────────────────────────────────────

def render_list():
    global _current_customer_id, _active_subview
    _current_customer_id = None

    if _active_subview == "registry":
        app.render("tpl-customers-shell", {"active_subview": "registry"})
        _bind_shell()
    else:
        _render_retention_view()


def render_detail(customer_id):
    global _current_customer_id, _active_subview
    _active_subview = "registry"  # Always snap back to registry when looking up details

    if not document.getElementById("cust-detail-panel"):
        app.render("tpl-customers-shell", {"active_subview": "registry"})
        _bind_shell()

    _current_customer_id = customer_id
    _mark_selected(customer_id)
    _load_detail_panel(customer_id)


# ── Retention View ─────────────────────────────────────────────────────────────

def _render_retention_view():
    try:
        raw = api.get(f"{BASE}/customers/retention")
        customers = raw.get("customers", [])
        status_map = {
            "Active": "paid",
            "Lapsing": "awaiting_approval",
            "Inactive": "voided",
        }
        for c in customers:
            c["total_spent_fmt"] = currency(c.get("total_spent"))
            c["avg_ticket_fmt"] = currency(c.get("avg_ticket"))
            c["days_since_label"] = human_days_ago(c.get("days_since"))
            c["status_class"] = status_map.get(c.get("status", ""), "draft")

    except api.ApiError as err:
        app.toast(f"Error loading retention metrics: {err.message}", "error")
        return

    app.render("tpl-customers-shell", {
        "active_subview": "retention",
        "retention_customers": customers
    })
    _bind_shell()


# ── Shell ──────────────────────────────────────────────────────────────────────

def _bind_shell():
    # Bind registry/retention subview selector buttons
    btn_reg_tab = document.getElementById("btn-cust-registry-tab")
    if btn_reg_tab:
        def _reg_click(ev):
            global _active_subview
            _active_subview = "registry"
            render_list()
        btn_reg_tab.bind("click", _reg_click)

    btn_ret_tab = document.getElementById("btn-cust-retention-tab")
    if btn_ret_tab:
        def _ret_click(ev):
            global _active_subview
            _active_subview = "retention"
            render_list()
        btn_ret_tab.bind("click", _ret_click)

    # Bind registry-specific fields if visible
    btn_new = document.getElementById("btn-new-customer")
    if btn_new:
        btn_new.bind("click", lambda evt: _render_customer_form())

    search = document.getElementById("customer-search")
    if search:
        search.focus()
        timer = {"id": None}

        def _run_search(query):
            def _done(data, error):
                if error:
                    app.toast(f"Search error: {error}", "error")
                    return
                _populate_list(data.get("customers", []))
                footer = document.getElementById("new-customer-footer")
                if footer:
                    footer.style.display = ""
            _fetch(f"{BASE}/customers?q={query}", _done)

        def _on_input(evt):
            query = evt.target.value.strip()
            if timer["id"] is not None:
                window.clearTimeout(timer["id"])
                timer["id"] = None
            if len(query) < 2:
                items = document.getElementById("customer-list-items")
                if items:
                    items.html = "<p class='empty cust-empty-hint'>Type to search customers.</p>"
                footer = document.getElementById("new-customer-footer")
                if footer:
                    footer.style.display = "none"
                return
            timer["id"] = window.setTimeout(lambda: _run_search(query), 300)

        search.bind("input", _on_input)

    btn_new_2 = document.getElementById("btn-new-customer-2")
    if btn_new_2:
        btn_new_2.bind("click", lambda evt: _render_customer_form())

    # Bind retention-specific customer clicks to navigate to details
    for lnk in document.select(".lnk-retention-customer"):
        cid = int(lnk.getAttribute("data-id"))
        def _make_lnk_handler(c_id):
            def _click(evt):
                evt.preventDefault()
                window.location.hash = f"#/customers/{c_id}"
            return _click
        lnk.bind("click", _make_lnk_handler(cid))


def _populate_list(customers):
    rows = []
    for cust in customers:
        first = cust.get("first_name", "")
        last = cust.get("last_name", "")
        rows.append({
            "id": cust["id"],
            "initials": ((first or "")[:1] + (last or "")[:1]).upper() or "?",
            "name": f"{last}, {first}".strip(", ") or "—",
            "contact_val": cust.get("phone") or cust.get("email") or "—",
            "customer_type": cust.get("customer_type", "").title(),
            "is_selected": cust["id"] == _current_customer_id,
        })
    document.getElementById("customer-list-items").html = app.render_partial(
        "tpl-customers-list-items", {"customers": rows, "empty_msg": "No customers found."}
    )
    for item in document.select(".cust-list-item"):
        cid = int(item.getAttribute("data-id"))
        def _handler(c):
            def _click(evt):
                window.location.hash = f"#/customers/{c}"
            return _click
        item.bind("click", _handler(cid))


def _mark_selected(customer_id):
    for item in document.select(".cust-list-item"):
        cid = int(item.getAttribute("data-id"))
        if cid == customer_id:
            item.classList.add("selected")
        else:
            item.classList.remove("selected")


# ── Detail panel ───────────────────────────────────────────────────────────────

def _load_detail_panel(customer_id):
    document.getElementById("cust-detail-panel").html = \
        "<div class='cust-detail-empty'><p class='muted'>Loading…</p></div>"

    def _done(data, error):
        if error:
            app.toast(f"Error: {error}", "error")
            return
        _render_detail_panel(customer_id, data)

    _fetch(f"{BASE}/customers/{customer_id}", _done)


def _render_detail_panel(customer_id, data):
    cust = data.get("customer", {})
    first = cust.get("first_name", "")
    last = cust.get("last_name", "")

    equipment_data = []
    for eq in data.get("equipment", []):
        parts = [str(eq.get("year") or ""), eq.get("make", ""), eq.get("model", "")]
        equipment_data.append({
            "id": eq["id"],
            "year_make_model": " ".join(p for p in parts if p).strip() or "Unknown",
            "serial_number": eq.get("serial_number") or "—",
        })

    wo_rows = []
    for wo in data.get("work_orders", []):
        wo_obj = wo.get("work_order", {}) or wo
        equip_obj = wo.get("equipment") or {}
        status = wo_obj.get("status", "")
        problem = wo_obj.get("reported_problem") or wo.get("reported_problem") or ""
        make = equip_obj.get("make") or wo.get("make") or ""
        model = equip_obj.get("model") or wo.get("model") or ""
        wo_rows.append({
            "id": wo_obj.get("id") or wo.get("id"),
            "equip_label": f"{make} {model}".strip(),
            "problem_preview": problem[:60] + ("…" if len(problem) > 60 else ""),
            "status": status,
            "status_label": STATUS_LABELS.get(status, status),
            "date_in": str(wo_obj.get("date_in") or wo.get("date_in") or "")[:10],
            "is_active": status in ACTIVE_STATUSES,
        })

    sale_rows = []
    for sale in data.get("retail_sales", []):
        try:
            total_fmt = f"${float(sale.get('total', 0)):.2f}"
        except Exception:
            total_fmt = "$0.00"
        sale_rows.append({
            "id": sale["id"],
            "sale_date": str(sale.get("sale_date", ""))[:10],
            "total_fmt": total_fmt,
            "status": sale.get("status", ""),
        })

    document.getElementById("cust-detail-panel").html = app.render_partial(
        "tpl-customers-detail-panel", {
            "customer_id": customer_id,
            "initials": ((first or "")[:1] + (last or "")[:1]).upper() or "?",
            "first_name": first,
            "last_name": last,
            "phone": cust.get("phone", ""),
            "email": cust.get("email", ""),
            "notes": cust.get("notes", ""),
            "customer_type_is_commercial": cust.get("customer_type") == "commercial",
            "equipment": equipment_data,
            "work_orders": wo_rows,
            "retail_sales": sale_rows,
            "contact_logs": data.get("contact_logs", []),
        }
    )

    document.getElementById("btn-edit-customer").bind(
        "click", lambda evt: _render_customer_form(customer_id, cust)
    )
    document.getElementById("btn-add-equipment").bind(
        "click", lambda evt: _render_equipment_form(customer_id)
    )
    document.getElementById("btn-add-contact").bind(
        "click", lambda evt: _render_contact_form(customer_id)
    )

    for eq in equipment_data:
        eq_id = eq["id"]
        def _make_eq_handler(eid):
            def _click(evt):
                _edit_equipment(customer_id, eid)
            return _click
        document.getElementById(f"btn-edit-equip-{eq_id}").bind("click", _make_eq_handler(eq_id))


def _edit_equipment(customer_id, equipment_id):
    def _done(data, error):
        if error:
            app.toast(f"Error: {error}", "error")
            return
        for eq in data.get("equipment", []):
            if eq["id"] == equipment_id:
                _render_equipment_form(customer_id, equipment_id, eq)
                return
    _fetch(f"{BASE}/customers/{customer_id}", _done)


# ── Customer form (modal) ──────────────────────────────────────────────────────

def _render_customer_form(customer_id=None, prefill=None):
    prefill = prefill or {}
    app.modal(
        "Edit Customer" if customer_id else "New Customer",
        app.render_partial("tpl-customer-form", {
            "first_name": prefill.get("first_name", ""),
            "last_name": prefill.get("last_name", ""),
            "phone": prefill.get("phone", ""),
            "email": prefill.get("email", ""),
            "contact_preference": prefill.get("contact_preference", "call"),
            "customer_type": prefill.get("customer_type", "residential"),
            "address": prefill.get("address", ""),
            "city": prefill.get("city", ""),
            "state": prefill.get("state", "TX"),
            "zip_code": prefill.get("zip_code", ""),
            "notes": prefill.get("notes", ""),
        })
    )
    document.getElementById("form-customer").bind(
        "submit", lambda evt: _submit_customer_form(evt, customer_id)
    )
    document.getElementById("btn-cancel-customer").bind("click", lambda evt: app.close_modal())


def _submit_customer_form(event, customer_id=None):
    event.preventDefault()
    data = form_data("#form-customer")
    try:
        if customer_id:
            api.update_customer(customer_id, data)
            app.close_modal()
            app.toast("Customer updated", "success")
            _load_detail_panel(customer_id)
        else:
            result = api.create_customer(data)
            app.close_modal()
            app.toast("Customer created", "success")
            window.location.hash = f"#/customers/{result['id']}"
    except api.ApiError as err:
        app.toast(f"Error: {err.message}", "error")


# ── Equipment form (modal) ─────────────────────────────────────────────────────

def _render_equipment_form(customer_id, equipment_id=None, prefill=None):
    prefill = prefill or {}
    current_cat = prefill.get("category", EQUIPMENT_CATEGORIES[0][0])
    app.modal(
        "Edit Equipment" if equipment_id else "Add Equipment",
        app.render_partial("tpl-equipment-form", {
            "categories": [
                {"value": val, "label": label, "is_selected": val == current_cat}
                for val, label in EQUIPMENT_CATEGORIES
            ],
            "make": prefill.get("make", ""),
            "model": prefill.get("model", ""),
            "serial_number": prefill.get("serial_number", ""),
            "year": prefill.get("year", ""),
            "notes": prefill.get("notes", ""),
        })
    )
    document.getElementById("form-equipment").bind(
        "submit", lambda evt: _submit_equipment_form(evt, customer_id, equipment_id)
    )
    document.getElementById("btn-cancel-equip").bind("click", lambda evt: app.close_modal())


def _submit_equipment_form(event, customer_id, equipment_id=None):
    event.preventDefault()
    data = form_data("#form-equipment")
    try:
        if equipment_id:
            api.update_equipment(customer_id, equipment_id, data)
            app.close_modal()
            app.toast("Equipment updated", "success")
        else:
            api.create_equipment(customer_id, data)
            app.close_modal()
            app.toast("Equipment added", "success")
        _load_detail_panel(customer_id)
    except api.ApiError as err:
        app.toast(f"Error: {err.message}", "error")


# ── Customer Contact Log Form (modal) ──────────────────────────────────────────

def _render_contact_form(customer_id):
    today_str = str(datetime.date.today())
    app.modal(
        "Log Customer Contact",
        app.render_partial("tpl-contact-form", {
            "today": today_str
        })
    )
    document.getElementById("form-contact-log").bind(
        "submit", lambda evt: _submit_contact_form(evt, customer_id)
    )
    document.getElementById("btn-cancel-contact").bind("click", lambda evt: app.close_modal())


def _submit_contact_form(event, customer_id):
    event.preventDefault()
    data = form_data("#form-contact-log")
    try:
        api.post(f"{BASE}/customers/{customer_id}/contacts", data)
        app.close_modal()
        app.toast("Interaction logged", "success")
        _load_detail_panel(customer_id)
    except api.ApiError as err:
        app.toast(f"Error: {err.message}", "error")
