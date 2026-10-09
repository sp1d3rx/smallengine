"""Parts inventory page — list, detail, add/edit, and stock adjustment workflows."""
from browser import document, window

import api
import app
from gantrika import (
    currency,
    delta_qty,
    form_data,
    safe_action,
    short_date,
)
from constants import EQUIPMENT_CATEGORIES, EQUIPMENT_CATEGORY_LABELS

REASON_LABELS = {
    "count": "Inventory Counted",
    "physical_count": "Inventory Counted",
    "work_order": "Work Order",
    "wo": "Work Order",
    "purchase": "Purchase Order",
    "purchase_order": "Purchase Order",
    "po": "Purchase Order",
    "write_off": "Write-Off / Damage",
    "return": "Customer Return",
    "retail": "Retail Sale",
    "retail_sale": "Retail Sale",
    "other": "Manual Adjustment",
}


def _part_rows(parts_raw):
    """Convert raw API part dicts to template-ready row dicts."""
    rows = []
    for part in parts_raw:
        qty = part.get("qty_on_hand", 0) or 0
        reorder = part.get("reorder_point", 0) or 0
        rows.append({
            "id": part["id"],
            "part_number": part.get("part_number", ""),
            "description": part.get("description", ""),
            "qty_on_hand": qty,
            "is_low": qty <= reorder,
            "cost_fmt": currency(part.get("cost")),
            "price_fmt": currency(part.get("price")),
        })
    return rows


def render_list(filter_name=None):
    """Render parts inventory list page."""
    low_stock = filter_name == "low"
    try:
        data = api.list_parts(low_stock=low_stock)
    except api.ApiError as err:
        app.toast(f"Error loading parts: {err.message}", "error")
        return

    parts = data.get("parts", [])
    rows = _part_rows(parts)

    app.render("tpl-parts-list", {
        "parts": rows,
        "all_tab_active": not low_stock,
        "low_tab_active": low_stock,
        "empty_msg": "No low-stock parts." if low_stock else "No parts in catalog.",
    })

    btn_new = document.getElementById("btn-new-part")
    if btn_new:
        btn_new.bind("click", lambda evt: _show_part_form())

    tab_all = document.getElementById("tab-all")
    if tab_all:
        tab_all.bind("click", lambda evt: setattr(window.location, "hash", "#/parts"))

    tab_low = document.getElementById("tab-low")
    if tab_low:
        tab_low.bind("click", lambda evt: setattr(window.location, "hash", "#/parts?filter=low"))

    search_input = document.getElementById("parts-search")
    if search_input:
        search_timer = [None]

        def _on_search(evt):
            if search_timer[0] is not None:
                window.clearTimeout(search_timer[0])
            search_timer[0] = window.setTimeout(_do_search, 250)

        def _do_search():
            q = search_input.value.strip()
            try:
                result = api.list_parts(q=q, low_stock=low_stock)
                new_rows = _part_rows(result.get("parts", []))
                tbody = document.getElementById("parts-tbody")
                if tbody:
                    tbody.html = app.render_partial("tpl-parts-tbody", {
                        "parts": new_rows,
                        "empty_msg": "No parts match your search." if q else "No parts in catalog.",
                    })
            except api.ApiError as err:
                app.toast(f"Search error: {err.message}", "error")

        search_input.bind("input", _on_search)


def render_detail(part_id):
    """Render part detail page with inventory levels and stock adjustments."""
    try:
        data = api.get_part(part_id)
    except api.ApiError as err:
        app.toast(f"Error loading part: {err.message}", "error")
        return

    part = data.get("part", {})
    adjustments_raw = data.get("adjustments", [])
    qty = part.get("qty_on_hand", 0) or 0
    reorder = part.get("reorder_point", 0) or 0

    adj_rows = []
    for adj in adjustments_raw:
        delta = adj.get("delta", 0) or 0
        raw_reason = (adj.get("reason") or "").lower()
        reason_label = REASON_LABELS.get(raw_reason, (adj.get("reason") or "").replace("_", " ").title() or "Adjustment")
        ref_id = adj.get("reference_id")
        ref_name = adj.get("reference_name")
        ref_url = adj.get("reference_url")

        if not ref_url:
            if raw_reason in ("work_order", "wo") and ref_id:
                ref_name = ref_name or f"WO #{ref_id}"
                ref_url = f"#/workorders/{ref_id}"
            elif raw_reason in ("purchase", "purchase_order", "po") and ref_id:
                ref_name = ref_name or f"PO #{ref_id}"
                ref_url = f"#/purchasing/{ref_id}"

        adj_rows.append({
            "date": short_date(adj.get("created_on")),
            "reason_label": reason_label,
            "ref_name": ref_name,
            "ref_url": ref_url,
            "delta_class": "delta-positive" if delta > 0 else "delta-negative",
            "delta_fmt": delta_qty(delta),
        })

    compatible = part.get("compatible_categories", "")
    if compatible:
        cat_labels = [
            EQUIPMENT_CATEGORY_LABELS.get(cat.strip(), cat.strip())
            for cat in compatible.split(",") if cat.strip()
        ]
        compatible_display = ", ".join(cat_labels) if cat_labels else "—"
    else:
        compatible_display = "—"

    supplier_id = part.get("supplier_id")
    app.render("tpl-parts-detail", {
        "part_id": part_id,
        "part_number": part.get("part_number", ""),
        "description": part.get("description", ""),
        "is_low": qty <= reorder,
        "qty_on_hand": qty,
        "reorder_point": reorder,
        "reorder_qty": part.get("reorder_qty", 0) or 0,
        "cost_fmt": currency(part.get("cost")),
        "price_fmt": currency(part.get("price")),
        "adjustments": adj_rows,
        "compatible_display": compatible_display,
        "has_supplier": bool(supplier_id),
        "supplier_id": supplier_id,
        "supplier_name": part.get("supplier_name") or "View Supplier",
        "is_active_label": "Yes" if part.get("active") else "No",
    })

    btn_edit = document.getElementById("btn-edit-part")
    if btn_edit:
        btn_edit.bind("click", lambda evt: _show_part_form(part))

    btn_adj = document.getElementById("btn-adjust")
    if btn_adj:
        btn_adj.bind("click", lambda evt: _show_adjust_form(part_id))


def _show_part_form(part=None):
    is_edit = part is not None
    part = part or {}

    supplier_rows = []
    try:
        sup_data = api.list_suppliers()
        current_sup_id = str(part.get("supplier_id") or "")
        for supplier in sup_data.get("suppliers", []):
            supplier_rows.append({
                "id": supplier["id"],
                "name": supplier["name"],
                "is_selected": str(supplier["id"]) == current_sup_id,
            })
    except api.ApiError:
        pass

    compat_values = set(part.get("compatible_categories", "").split(","))
    category_rows = [
        {"value": val, "label": label, "is_selected": val in compat_values}
        for val, label in EQUIPMENT_CATEGORIES
    ]

    part_id = part.get("id", "")
    app.render("tpl-parts-form", {
        "title": "Edit Part" if is_edit else "Add Part",
        "back_href": f"#/parts/{part_id}" if part_id else "#/parts",
        "part_number": part.get("part_number", ""),
        "description": part.get("description", ""),
        "cost": part.get("cost", 0),
        "price": part.get("price", 0),
        "qty_on_hand": part.get("qty_on_hand", 0),
        "reorder_point": part.get("reorder_point", 0),
        "reorder_qty": part.get("reorder_qty", 0),
        "suppliers": supplier_rows,
        "categories": category_rows,
    })

    form = document.getElementById("form-part")
    if form:
        def _on_success(res):
            if is_edit:
                render_detail(part_id)
            else:
                window.location.hash = f"#/parts/{res['id']}"

        @safe_action("Part updated" if is_edit else "Part created", on_success=_on_success)
        def _submit(evt):
            payload = form_data("#form-part")
            cat_els = form.select("[name=compatible_categories] option")
            payload["compatible_categories"] = ",".join(opt.value for opt in cat_els if opt.selected)
            payload["cost"] = float(payload.get("cost") or 0)
            payload["price"] = float(payload.get("price") or 0)
            payload["qty_on_hand"] = int(payload.get("qty_on_hand") or 0)
            payload["reorder_point"] = int(payload.get("reorder_point") or 0)
            payload["reorder_qty"] = int(payload.get("reorder_qty") or 0)
            if payload.get("supplier_id"):
                payload["supplier_id"] = int(payload["supplier_id"])
            if is_edit:
                api.update_part(part_id, payload)
                return {"id": part_id}
            else:
                return api.create_part(payload)

        form.bind("submit", _submit)


def _show_adjust_form(part_id):
    adj_div = document.getElementById("adjust-area")
    if not adj_div:
        return
    adj_div.html = app.render_partial("tpl-parts-adjust-form", {})
    form = document.getElementById("form-adjust")
    if form:
        @safe_action("Stock adjusted", on_success=lambda _: render_detail(part_id))
        def _submit(evt):
            data = form_data("#form-adjust")
            delta_val = data.get("delta") or 0
            reason = data.get("reason") or "count"
            api.adjust_part_stock(part_id, int(delta_val), reason)

        form.bind("submit", _submit)

    cancel = document.getElementById("btn-cancel-adj")
    if cancel:
        cancel.bind("click", lambda evt: render_detail(part_id))
