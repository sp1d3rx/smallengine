"""Work orders — role-based queue list and intake form."""

import app
import api
from gantrika import form_data
from browser import document, window
from constants import EQUIPMENT_CATEGORY_LABELS, WO_STATUS_LABELS as STATUS_LABELS

_STATUS_PRIORITY = {
    "in_repair": 1,
    "awaiting_approval": 2,
    "diagnosed": 3,
    "awaiting_parts": 4,
    "intake": 5,
    "ready": 6,
}
_ACTIVE_STATUSES = "intake,diagnosed,awaiting_approval,in_repair,awaiting_parts,ready"


# ── List ──────────────────────────────────────────────────────────────────────

_active_filter = "active"  # mutable global state


def render_list(filter_name=None):
    global _active_filter
    if filter_name is not None:
        _active_filter = filter_name

    status_param = None
    if _active_filter == "active":
        status_param = _ACTIVE_STATUSES
    elif _active_filter == "completed":
        status_param = "closed,cancelled"

    try:
        # Cap the completed view so the full work-order history isn't loaded on every render.
        # desc=1 makes the server return the most recent 200 (newest first).
        completed = _active_filter == "completed"
        data = api.list_work_orders(
            status=status_param,
            limit=200 if completed else None,
            desc="1" if completed else None,
        )
    except api.ApiError as err:
        app.toast(f"Error: {err.message}", "error")
        return

    work_orders = data.get("work_orders", [])

    if _active_filter == "active":
        work_orders.sort(
            key=lambda wo: (
                _STATUS_PRIORITY.get(wo.get("status", ""), 99),
                wo.get("date_promised") or "9999-99-99",
            )
        )
    elif _active_filter == "completed":
        work_orders.sort(
            key=lambda wo: wo.get("date_out") or wo.get("date_in") or "0000-00-00",
            reverse=True,
        )
    else:
        work_orders.sort(key=lambda wo: wo.get("id", 0), reverse=True)

    from datetime import date

    today = str(date.today())

    rows = []
    for wo in work_orders:
        status = wo.get("status", "")
        cust = wo.get("customer") or {}
        equip = wo.get("equipment") or {}
        emp = wo.get("employee") or {}
        promised = wo.get("date_promised") or ""
        is_overdue = bool(
            promised and promised < today and status not in ("closed", "cancelled")
        )
        rows.append(
            {
                "id": wo["id"],
                "customer_name": f"{cust.get('last_name', '')}, {cust.get('first_name', '')}".strip(
                    ", "
                ),
                "equip_desc": f"{equip.get('make', '')} {equip.get('model', '')}".strip()
                or "—",
                "work_type": wo.get("work_type", "").title(),
                "status": status,
                "status_label": STATUS_LABELS.get(status, status),
                "date_promised": promised,
                "date_out": str(wo.get("date_out") or "")[:10],
                "tech_name": f"{emp.get('first_name', '')} {emp.get('last_name', '')}".strip()
                or "—",
                "is_overdue": is_overdue,
            }
        )

    app.render(
        "tpl-workorders-list", {"work_orders": rows, "active_filter": _active_filter}
    )
    _bind_list_events()


def _bind_list_events():
    btn_active = document.getElementById("btn-wo-active")
    if btn_active:
        btn_active.bind("click", lambda ev: render_list("active"))

    btn_completed = document.getElementById("btn-wo-completed")
    if btn_completed:
        btn_completed.bind("click", lambda ev: render_list("completed"))

    btn_all = document.getElementById("btn-wo-all")
    if btn_all:
        btn_all.bind("click", lambda ev: render_list("all"))


# ── Intake form ───────────────────────────────────────────────────────────────


def render_intake(prefill_customer_id=None, prefill_equipment_id=None):
    try:
        emp_data = api.list_employees()
        employees = emp_data.get("employees", [])
    except api.ApiError:
        employees = []

    emp_rows = [
        {"id": emp["id"], "name": f"{emp['first_name']} {emp['last_name']}"}
        for emp in employees
    ]

    try:
        settings_data = api.get("/shop/api/settings")
        default_threshold = float(
            settings_data.get("settings", {}).get("estimate_approval_threshold", 100.0)
        )
        default_approval_threshold = f"{default_threshold:.2f}"
    except Exception:
        default_approval_threshold = "100.00"

    app.render(
        "tpl-workorders-intake",
        {
            "employees": emp_rows,
            "default_promise": default_promise,
            "default_approval_threshold": default_approval_threshold,
        },
    )

    _bind_intake(prefill_customer_id, prefill_equipment_id)


def _bind_intake(prefill_customer_id, prefill_equipment_id):
    state = {"customer_id": None, "equipment_id": None}

    def set_equipment(equipment_id):
        state["equipment_id"] = equipment_id
        _refresh_submit(state)

    def set_customer(customer_id):
        state["customer_id"] = customer_id
        state["equipment_id"] = None
        _refresh_submit(state)
        if customer_id:
            _load_equipment_picker(customer_id, set_equipment, prefill_equipment_id)

    search_el = document.getElementById("customer-search-input")
    if search_el:

        def _on_search(evt):
            query = evt.target.value.strip()
            results_div = document.getElementById("customer-search-results")
            if not results_div:
                return
            if len(query) < 2:
                results_div.classList.add("hidden")
                return
            try:
                customers = api.list_customers(q=query).get("customers", [])
                _render_customer_results(customers, set_customer)
            except api.ApiError:
                pass

        search_el.bind("input", _on_search)

        def _on_blur(evt):
            results_div = document.getElementById("customer-search-results")
            if results_div:
                # Small delay so a click on a result still fires before hiding
                window.setTimeout(lambda: results_div.classList.add("hidden"), 150)

        search_el.bind("blur", _on_blur)

    btn_new = document.getElementById("btn-new-customer-inline")
    if btn_new:
        btn_new.bind("click", lambda evt: _inline_customer_form(set_customer))

    wt_select = document.getElementById("intake-work-type")
    if wt_select:

        def _on_type_change(evt):
            try:
                pd = api.get_promise_date(evt.target.value).get("date", "")
                el = document.getElementById("intake-promise")
                if el:
                    el.value = pd
            except api.ApiError:
                pass

        wt_select.bind("change", _on_type_change)

    btn_submit = document.getElementById("btn-submit-intake")
    if btn_submit:
        btn_submit.bind("click", lambda evt: _submit_intake(state))

    if prefill_customer_id:
        try:
            cust = api.get_customer(prefill_customer_id).get("customer", {})
            _show_selected_customer(cust, prefill_customer_id, set_customer)
            set_customer(prefill_customer_id)
        except api.ApiError:
            pass


def _refresh_submit(state):
    btn = document.getElementById("btn-submit-intake")
    if not btn:
        return
    if state["customer_id"] and state["equipment_id"]:
        btn.removeAttribute("disabled")
    else:
        btn.setAttribute("disabled", "")


def _render_customer_results(customers, on_select):
    results_div = document.getElementById("customer-search-results")
    if not results_div:
        return
    rows = []
    for cust in customers[:8]:
        contact = cust.get("phone") or cust.get("email") or ""
        rows.append(
            {
                "id": cust["id"],
                "first_name": cust.get("first_name", ""),
                "last_name": cust.get("last_name", ""),
                "contact": contact,
            }
        )
    results_div.html = app.render_partial(
        "tpl-intake-customer-results", {"customers": rows}
    )
    results_div.classList.remove("hidden")
    for item in results_div.select(".search-result-item[data-id]"):
        cid = int(item.getAttribute("data-id"))

        def _make_handler(cid=cid):
            def _click(evt):
                results_div.classList.add("hidden")
                try:
                    cust = api.get_customer(cid).get("customer", {})
                    _show_selected_customer(cust, cid, on_select)
                    on_select(cid)
                except api.ApiError as err:
                    app.toast(f"Error: {err.message}", "error")

            return _click

        item.bind("click", _make_handler())


def _show_selected_customer(cust, customer_id, on_select):
    search_el = document.getElementById("customer-search-input")
    btn_new = document.getElementById("btn-new-customer-inline")
    card = document.getElementById("customer-selected")
    if search_el:
        search_el.classList.add("hidden")
    if btn_new:
        btn_new.classList.add("hidden")
    if card:
        contact = cust.get("phone") or cust.get("email") or "—"
        card.html = app.render_partial(
            "tpl-intake-selected-customer",
            {
                "first_name": cust.get("first_name", ""),
                "last_name": cust.get("last_name", ""),
                "contact": contact,
            },
        )
        card.classList.remove("hidden")
        change_btn = document.getElementById("btn-change-cust")
        if change_btn:

            def _change(evt):
                card.classList.add("hidden")
                if search_el:
                    search_el.value = ""
                    search_el.classList.remove("hidden")
                if btn_new:
                    btn_new.classList.remove("hidden")
                picker = document.getElementById("equipment-picker")
                if picker:
                    picker.html = app.render_partial("tpl-intake-picker-empty", {})
                on_select(None)

            change_btn.bind("click", _change)


def _inline_customer_form(on_created):
    body = app.render_partial(
        "tpl-customer-form",
        {
            "first_name": "",
            "last_name": "",
            "phone": "",
            "email": "",
            "contact_preference": "call",
            "customer_type": "residential",
            "address": "",
            "city": "",
            "state": "TX",
            "zip_code": "",
            "notes": "",
        },
    )
    app.modal("New Customer", body)

    form = document.getElementById("form-customer")
    if form:

        def _submit(evt):
            evt.preventDefault()
            data = form_data("#form-customer")
            try:
                new_id = api.create_customer(data)["id"]
                cust = api.get_customer(new_id).get("customer", {})
                app.close_modal()
                _show_selected_customer(cust, new_id, on_created)
                on_created(new_id)
                app.toast("Customer created", "success")
            except api.ApiError as err:
                app.toast(f"Error: {err.message}", "error")

        form.bind("submit", _submit)

    cancel = document.getElementById("btn-cancel-customer")
    if cancel:
        cancel.bind("click", lambda evt: app.close_modal())


def _load_equipment_picker(customer_id, on_select, prefill_equipment_id=None):
    picker = document.getElementById("equipment-picker")
    if not picker:
        return
    try:
        data = api.get_customer(customer_id)
        equipment_list = data.get("equipment", [])
    except api.ApiError as err:
        picker.html = app.render_partial(
            "tpl-intake-picker-error", {"message": err.message}
        )
        return

    if not prefill_equipment_id and len(equipment_list) == 1:
        prefill_equipment_id = equipment_list[0]["id"]

    equip_rows = []
    for eq in equipment_list:
        cat = EQUIPMENT_CATEGORY_LABELS.get(eq.get("category", ""), "")
        year = eq.get("year") or ""
        desc = f"{year} {eq.get('make', '')} {eq.get('model', '')}".strip()
        sn = f" S/N:{eq['serial_number']}" if eq.get("serial_number") else ""
        equip_rows.append(
            {
                "id": eq["id"],
                "label": f"{desc} ({cat}){sn}",
                "is_selected": eq["id"] == prefill_equipment_id,
            }
        )

    picker.html = app.render_partial(
        "tpl-intake-equipment-picker", {"equipment": equip_rows}
    )

    equip_select = document.getElementById("equipment-select")
    if equip_select:
        if prefill_equipment_id:
            on_select(prefill_equipment_id)

        def _on_change(evt):
            val = evt.target.value
            on_select(int(val) if val else None)

        equip_select.bind("change", _on_change)

    btn_add = document.getElementById("btn-add-equip-inline")
    if btn_add:
        btn_add.bind(
            "click", lambda evt: _inline_equipment_form(customer_id, on_select)
        )


def _inline_equipment_form(customer_id, on_select):
    form_div = document.getElementById("new-equip-form")
    if not form_div:
        return
    from constants import EQUIPMENT_CATEGORIES

    cat_rows = [{"value": val, "label": label} for val, label in EQUIPMENT_CATEGORIES]
    form_div.html = app.render_partial(
        "tpl-intake-equipment-form", {"categories": cat_rows}
    )
    form = document.getElementById("form-equip-inline")
    if form:

        def _submit(evt):
            evt.preventDefault()
            data = form_data("#form-equip-inline")
            try:
                new_id = api.create_equipment(customer_id, data)["id"]
                app.toast("Equipment added", "success")
                _load_equipment_picker(
                    customer_id, on_select, prefill_equipment_id=new_id
                )
            except api.ApiError as err:
                app.toast(f"Error: {err.message}", "error")

        form.bind("submit", _submit)
    cancel = document.getElementById("btn-cancel-equip-inline")
    if cancel:
        cancel.bind("click", lambda evt: setattr(form_div, "html", ""))


def _submit_intake(state):
    customer_id = state.get("customer_id")
    equipment_id = state.get("equipment_id")
    if not customer_id or not equipment_id:
        app.toast("Select a customer and equipment first.", "error")
        return

    problem_el = document.getElementById("intake-problem")
    wt_el = document.getElementById("intake-work-type")
    emp_el = document.getElementById("intake-employee")
    promise_el = document.getElementById("intake-promise")
    notes_el = document.getElementById("intake-notes")
    limit_el = document.getElementById("intake-approval-limit")
    est_el = document.getElementById("intake-estimated-cost")

    problem = problem_el.value.strip() if problem_el else ""
    if not problem:
        app.toast("Enter the customer's complaint.", "error")
        return

    data = {
        "customer_id": customer_id,
        "equipment_id": equipment_id,
        "reported_problem": problem,
        "work_type": wt_el.value if wt_el else "repair",
        "employee_id": int(emp_el.value) if emp_el and emp_el.value else None,
        "date_promised": promise_el.value if promise_el and promise_el.value else None,
        "notes": notes_el.value.strip() if notes_el else "",
    }
    if limit_el and limit_el.value.strip():
        try:
            data["pre_approved_limit"] = float(limit_el.value)
        except Exception:
            pass
    if est_el and est_el.value.strip():
        try:
            data["estimated_cost"] = float(est_el.value)
        except Exception:
            pass

    try:
        result = api.create_work_order(data)
        app.toast("Work order created", "success")
        window.location.hash = f"#/workorders/{result['id']}"
    except api.ApiError as err:
        app.toast(f"Error: {err.message}", "error")
