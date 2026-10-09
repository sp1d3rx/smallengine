"""Purchase orders page — list, create, detail + receiving."""
import app
import api
from gantrika import form_data, currency, short_date, safe_action
from browser import document, window
from constants import SHIPPING_METHODS, SHIPPING_METHOD_LABELS as SHIPPING_LABELS

STATUS_LABELS = {
    "draft": "Draft", "sent": "Sent", "partial": "Partial",
    "received": "Received", "cancelled": "Cancelled",
}


def render_list():
    try:
        data = api.list_purchase_orders()
    except api.ApiError as err:
        app.toast(f"Error: {err.message}", "error")
        return

    pos = data.get("purchase_orders", [])
    rows = [{
        "id": po["id"],
        "po_number": po.get("po_number", ""),
        "supplier_name": po.get("supplier_name", ""),
        "ordered_on": short_date(po.get("ordered_on")),
        "expected_by": short_date(po.get("expected_by")),
        "status_label": STATUS_LABELS.get(po.get("status", "draft"), po.get("status", "draft")),
        "total_fmt": currency(po.get("total")),
    } for po in pos]

    app.render("tpl-purchasing-list", {"pos": rows})


def render_detail(po_id):
    try:
        data = api.get_purchase_order(po_id)
    except api.ApiError as err:
        app.toast(f"Error: {err.message}", "error")
        return

    po = data.get("purchase_order", {})
    supplier = data.get("supplier", {})
    contact = data.get("primary_contact") or {}
    lines = data.get("lines", [])

    status = po.get("status", "draft")
    status_label = STATUS_LABELS.get(status, status)
    is_draft = status == "draft"
    is_receivable = status in ("sent", "partial")

    supplier_id = supplier.get("id", "")
    shipping = SHIPPING_LABELS.get(po.get("shipping_method", ""), po.get("shipping_method", "") or "—")

    lines_data = []
    for line in lines:
        remaining = (line.get("qty_ordered", 0) or 0) - (line.get("qty_received", 0) or 0)
        part_num = line.get("part_number", "")
        desc = line.get("description", "")
        display = f"{part_num} — {desc}" if part_num and part_num not in desc else desc
        lines_data.append({
            "line_id": line["id"],
            "display": display,
            "qty_ordered": line.get("qty_ordered", 0),
            "unit_cost_fmt": currency(line.get("unit_cost")),
            "total_cost_fmt": currency(line.get("total_cost")),
            "qty_received": line.get("qty_received", 0),
            "remaining": remaining,
            "is_receivable": is_receivable,
            "is_draft": is_draft,
        })

    contact_str = ""
    if contact:
        contact_str = contact.get("name", "")
        if contact.get("phone"):
            contact_str += f" · {contact['phone']}"

    app.render("tpl-purchasing-detail", {
        "po_number": po.get("po_number", ""),
        "status": status,
        "status_label": status_label,
        "is_draft": is_draft,
        "lines": lines_data,
        "total_fmt": currency(po.get("total")),
        "supplier_id": supplier_id,
        "supplier_name": supplier.get("name", ""),
        "contact_str": contact_str or "—",
        "ordered_on": short_date(po.get("ordered_on")),
        "expected_by": short_date(po.get("expected_by")),
        "shipping_label": shipping,
        "tracking": po.get("tracking_number", "") or "—",
        "notes": po.get("notes", "") or "—",
    })

    _bind_po_detail(po_id, po, lines, lines_data, is_draft, is_receivable)


def _bind_po_detail(po_id, po, lines, lines_data, is_draft, is_receivable):
    btn_sent = document.getElementById("btn-mark-sent")
    if btn_sent:
        def _mark_sent(evt):
            import datetime
            try:
                api.update_purchase_order(po_id, {
                    "status": "sent",
                    "ordered_on": str(datetime.date.today()),
                })
                app.toast("PO marked as sent", "success")
                render_detail(po_id)
            except api.ApiError as err:
                app.toast(f"Error: {err.message}", "error")
        btn_sent.bind("click", _mark_sent)

    btn_cancel = document.getElementById("btn-cancel-po")
    if btn_cancel:
        def _cancel(evt):
            if not window.confirm("Cancel this purchase order?"):
                return
            try:
                api.cancel_purchase_order(po_id)
                app.toast("PO cancelled", "success")
                render_detail(po_id)
            except api.ApiError as err:
                app.toast(f"Error: {err.message}", "error")
        btn_cancel.bind("click", _cancel)

    btn_receive = document.getElementById("btn-receive")
    if btn_receive:
        def _show_receive_modal(evt):
            receivable = [line for line in lines_data if line.get("remaining", 0) > 0]
            body_html = app.render_partial("tpl-po-receive-form", {"lines": receivable})
            app.modal("Receive Items", body_html)

            form = document.getElementById("form-receive")
            if form:
                def _submit(evt):
                    evt.preventDefault()
                    receipts = []
                    for inp in form.select(".recv-input"):
                        line_id = int(inp.getAttribute("data-line-id"))
                        qty = int(inp.value or 0)
                        if qty > 0:
                            receipts.append({"line_id": line_id, "qty_received": qty})
                    if not receipts:
                        app.toast("Enter at least one quantity", "info")
                        return
                    try:
                        api.receive_po(po_id, receipts)
                        app.toast("Stock received and updated", "success")
                        app.close_modal()
                        render_detail(po_id)
                    except api.ApiError as err:
                        app.toast(f"Error: {err.message}", "error")
                form.bind("submit", _submit)

            cancel = document.getElementById("btn-cancel-receive")
            if cancel:
                cancel.bind("click", lambda evt: app.close_modal())
        btn_receive.bind("click", _show_receive_modal)

    btn_add_line = document.getElementById("btn-add-line")
    if btn_add_line:
        btn_add_line.bind("click", lambda evt: _show_add_line_form(po_id))

    btn_edit = document.getElementById("btn-edit-po")
    if btn_edit:
        btn_edit.bind("click", lambda evt: _show_edit_po_form(po_id, po))

    for btn in document.select(".del-line-btn"):
        lid = int(btn.getAttribute("data-line-id"))
        def _make_del(line_id=lid):
            def _do(evt):
                if not window.confirm("Remove this line?"):
                    return
                try:
                    api.delete_po_line(po_id, line_id)
                    render_detail(po_id)
                except api.ApiError as err:
                    app.toast(f"Error: {err.message}", "error")
            return _do
        btn.bind("click", _make_del())


def _show_add_line_form(po_id):
    form_div = document.getElementById("add-line-form")
    if not form_div:
        return

    part_rows = []
    try:
        parts_data = api.list_parts()
        for part in parts_data.get("parts", []):
            part_num = part.get("part_number", "")
            desc = part.get("description", "")
            part_rows.append({
                "id": part["id"],
                "label": f"{part_num} — {desc}" if part_num else desc,
                "cost": part.get("cost", 0),
            })
    except api.ApiError:
        pass

    form_div.html = app.render_partial("tpl-po-add-line-form", {"parts": part_rows})

    part_sel = document.getElementById("line-part-select")
    cost_inp = document.getElementById("line-cost-input")
    if part_sel and cost_inp:
        def _on_part_change(evt):
            sel_opt = part_sel.options[part_sel.selectedIndex]
            cost_val = sel_opt.getAttribute("data-cost") or "0"
            cost_inp.value = cost_val
        part_sel.bind("change", _on_part_change)

    form = document.getElementById("form-add-line")
    if form:
        def _submit(evt):
            evt.preventDefault()
            payload = form_data("#form-add-line")
            payload["qty_ordered"] = int(payload.get("qty_ordered") or 1)
            payload["unit_cost"] = float(payload.get("unit_cost") or 0)
            if payload.get("part_id"):
                payload["part_id"] = int(payload["part_id"])
            try:
                api.add_po_line(po_id, payload)
                render_detail(po_id)
            except api.ApiError as err:
                app.toast(f"Error: {err.message}", "error")
        form.bind("submit", _submit)

    cancel = document.getElementById("btn-cancel-line")
    if cancel:
        cancel.bind("click", lambda evt: setattr(form_div, "html", ""))


def _show_edit_po_form(po_id, po):
    """Inline edit for shipping, tracking, expected date, notes."""
    shipping_methods = [
        {"value": val, "label": label, "is_selected": po.get("shipping_method") == val}
        for val, label in SHIPPING_METHODS
    ]

    info_card = document.querySelector(".bench-card[style*='max-width']")
    if not info_card:
        return

    info_card.html = app.render_partial("tpl-po-edit-form", {
        "shipping_methods": shipping_methods,
        "tracking": po.get("tracking_number", "") or "",
        "expected": str(po.get("expected_by", "") or ""),
        "notes": po.get("notes", "") or "",
    })

    form = document.getElementById("form-edit-po")
    if form:
        def _submit(evt):
            evt.preventDefault()
            payload = form_data("#form-edit-po")
            try:
                api.update_purchase_order(po_id, payload)
                app.toast("PO updated", "success")
                render_detail(po_id)
            except api.ApiError as err:
                app.toast(f"Error: {err.message}", "error")
        form.bind("submit", _submit)

    cancel = document.getElementById("btn-cancel-edit-po")
    if cancel:
        cancel.bind("click", lambda evt: render_detail(po_id))


def render_new_po(prefill_supplier_id=None, prefill_part_id=None):
    """Create new PO form."""
    suppliers = []
    try:
        sup_data = api.list_suppliers()
        for supplier in sup_data.get("suppliers", []):
            suppliers.append({
                "id": supplier["id"],
                "name": supplier["name"],
                "is_selected": str(supplier["id"]) == str(prefill_supplier_id or ""),
            })
    except api.ApiError:
        pass

    shipping_methods = [
        {"value": val, "label": label}
        for val, label in SHIPPING_METHODS
    ]

    app.render("tpl-purchasing-new", {
        "suppliers": suppliers,
        "shipping_methods": shipping_methods,
    })

    _bind_new_po_form(prefill_part_id)


def _bind_new_po_form(prefill_part_id=None):
    """Populate line container and bind all new-PO form events."""

    # Fetch parts once; reused for initial line and "add another"
    all_parts = []
    try:
        for part in api.list_parts().get("parts", []):
            part_num = part.get("part_number", "")
            desc = part.get("description", "")
            all_parts.append({
                "id": part["id"],
                "label": f"{part_num} — {desc}" if part_num else desc,
                "cost": part.get("cost", 0),
                "is_selected": False,
            })
    except api.ApiError:
        pass

    def _parts_with_selection(selected_id=None):
        selected_str = str(selected_id or "")
        return [dict(part, is_selected=(str(part["id"]) == selected_str)) for part in all_parts]

    def _recalc_total():
        total = 0.0
        costs = document.select(".line-cost")
        qtys = document.select(".line-qty")
        for idx in range(min(len(costs), len(qtys))):
            try:
                total += float(costs[idx].value or 0) * int(qtys[idx].value or 0)
            except Exception:
                pass
        el = document.getElementById("po-total-display")
        if el:
            el.html = f"${total:.2f}"

    def _bind_line_row_events():
        for sel in document.select(".line-part-sel"):
            def _on_change(evt):
                sel_el = evt.target
                opt = sel_el.options[sel_el.selectedIndex]
                cost_val = opt.getAttribute("data-cost") or "0"
                parent = sel_el.closest(".po-line-group")
                if parent:
                    inp = parent.querySelector(".line-cost")
                    if inp:
                        inp.value = cost_val
                _recalc_total()
            sel.bind("change", _on_change)
        for inp in document.select(".line-cost, .line-qty"):
            inp.bind("input", lambda evt: _recalc_total())
        for btn in document.select(".remove-line-btn"):
            def _make_remove(remove_btn=btn):
                def _do(evt):
                    group = remove_btn.closest(".po-line-group")
                    if group:
                        group.remove()
                    _recalc_total()
                return _do
            btn.bind("click", _make_remove())

    # Load prefill data and populate the initial line group
    prefill_part = None
    if prefill_part_id:
        try:
            prefill_part = api.get_part(int(prefill_part_id)).get("part", {})
        except api.ApiError:
            pass

    pfill_desc = ""
    pfill_cost = "0"
    pfill_qty = "1"
    if prefill_part:
        pfill_desc = f"{prefill_part.get('part_number', '')} — {prefill_part.get('description', '')}"
        pfill_cost = str(prefill_part.get("cost", 0) or 0)
        pfill_qty = str(prefill_part.get("reorder_qty", 1) or 1)

    container = document.getElementById("po-lines-container")
    if container:
        container.html = app.render_partial("tpl-po-line-group", {
            "parts": _parts_with_selection(prefill_part_id),
            "desc": pfill_desc,
            "cost_val": pfill_cost,
            "qty": pfill_qty,
        })

    btn_add = document.getElementById("btn-add-another-line")
    if btn_add:
        def _add_line(evt):
            container2 = document.getElementById("po-lines-container")
            if not container2:
                return
            new_group = document.createElement("div")
            new_group.className = "po-line-group"
            new_group.html = app.render_partial("tpl-po-line-group", {
                "parts": _parts_with_selection(),
                "desc": "",
                "cost_val": "0",
                "qty": "1",
            })
            container2 <= new_group
            _bind_line_row_events()
        btn_add.bind("click", _add_line)

    _bind_line_row_events()

    btn_create = document.getElementById("btn-create-po")
    if btn_create:
        def _create(evt):
            supplier_el = document.getElementById("po-supplier-sel")
            if not supplier_el or not supplier_el.value:
                app.toast("Select a supplier", "info")
                return
            supplier_id = int(supplier_el.value)

            po_lines = []
            for group in document.select(".po-line-group"):
                desc_els = group.select(".line-desc")
                qty_els = group.select(".line-qty")
                cost_els = group.select(".line-cost")
                part_els = group.select(".line-part-sel")
                desc = desc_els[0].value.strip() if desc_els else ""
                qty = int(qty_els[0].value or 1) if qty_els else 1
                cost = float(cost_els[0].value or 0) if cost_els else 0
                part_val = part_els[0].value if part_els else ""
                if not desc:
                    continue
                po_line = {"description": desc, "qty_ordered": qty, "unit_cost": cost}
                if part_val:
                    po_line["part_id"] = int(part_val)
                po_lines.append(po_line)

            if not po_lines:
                app.toast("Add at least one line item", "info")
                return

            ship_el = document.querySelector("[name=shipping_method]")
            exp_el = document.getElementById("po-expected")
            notes_el = document.getElementById("po-notes")

            payload = {
                "supplier_id": supplier_id,
                "lines": po_lines,
                "shipping_method": ship_el.value if ship_el else "",
                "notes": notes_el.value if notes_el else "",
            }
            if exp_el and exp_el.value:
                payload["expected_by"] = exp_el.value

            try:
                result = api.create_purchase_order(payload)
                app.toast(f"PO {result.get('po_number', '')} created", "success")
                render_detail(result["po_id"])
            except api.ApiError as err:
                app.toast(f"Error: {err.message}", "error")
        btn_create.bind("click", _create)
