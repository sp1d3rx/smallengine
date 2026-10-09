"""Suppliers page — list, detail with contacts and PO history."""
import app
import api
from gantrika import form_data
from browser import document, window
from constants import (
    SUPPLIER_TERMS, SUPPLIER_TERMS_LABELS as TERMS_LABELS,
    SHIPPING_METHODS, SHIPPING_METHOD_LABELS as SHIPPING_LABELS,
)


def render_list():
    try:
        data = api.list_suppliers()
    except api.ApiError as err:
        app.toast(f"Error: {err.message}", "error")
        return

    suppliers = data.get("suppliers", [])
    rows = []
    for supplier in suppliers:
        contact = supplier.get("primary_contact") or {}
        contact_str = contact.get("name", "") or ""
        if contact.get("phone"):
            contact_str += f" · {contact['phone']}"
        rows.append({
            "id": supplier["id"],
            "name": supplier.get("name", ""),
            "phone_display": supplier.get("phone", "") or "—",
            "contact_str": contact_str or "—",
            "terms_label": TERMS_LABELS.get(supplier.get("terms", ""), supplier.get("terms", "")),
            "account_number": supplier.get("account_number", "") or "—",
        })

    app.render("tpl-suppliers-list", {"suppliers": rows})

    btn = document.getElementById("btn-new-supplier")
    if btn:
        btn.bind("click", lambda evt: render_form())


def render_detail(supplier_id):
    try:
        data = api.get_supplier(supplier_id)
    except api.ApiError as err:
        app.toast(f"Error: {err.message}", "error")
        return

    supplier = data.get("supplier", {})
    contacts = data.get("contacts", [])
    pos = data.get("purchase_orders", [])

    contact_rows = []
    for contact in contacts:
        contact_rows.append({
            "id": contact["id"],
            "name": contact.get("name", ""),
            "title": contact.get("title", ""),
            "phone": contact.get("phone", ""),
            "email": contact.get("email", ""),
            "is_primary": bool(contact.get("is_primary")),
            "is_primary": bool(contact.get("is_primary")),
            "has_phone_and_email": bool(contact.get("phone") and contact.get("email")),
        })

    po_rows = []
    for po in pos[:10]:
        po_rows.append({
            "id": po["id"],
            "po_number": po.get("po_number", ""),
            "ordered_on": po.get("ordered_on", "") or "—",
            "status": po.get("status", "draft"),
            "total_fmt": f"${po.get('total', 0):.2f}",
        })

    app.render("tpl-suppliers-detail", {
        "supplier_id": supplier_id,
        "name": supplier.get("name", ""),
        "contacts": contact_rows,
        "pos": po_rows,
        "phone_display": supplier.get("phone", "") or "—",
        "email_display": supplier.get("email", "") or "—",
        "website_display": supplier.get("website", "") or "—",
        "account_number": supplier.get("account_number", "") or "—",
        "terms_label": TERMS_LABELS.get(supplier.get("terms", ""), supplier.get("terms", "")),
        "shipping_label": SHIPPING_LABELS.get(supplier.get("default_shipping", ""), supplier.get("default_shipping", "")),
        "notes": supplier.get("notes", ""),
    })

    _bind_supplier_detail(supplier_id, supplier, contacts)


def _bind_supplier_detail(supplier_id, supplier, contacts):
    btn_edit = document.getElementById("btn-edit-supplier")
    if btn_edit:
        btn_edit.bind("click", lambda evt: render_form(supplier))

    btn_add = document.getElementById("btn-add-contact")
    if btn_add:
        btn_add.bind("click", lambda evt: _show_contact_form(supplier_id))

    for btn in document.select(".edit-contact-btn"):
        cid = int(btn.getAttribute("data-contact-id"))
        contact = next((cont for cont in contacts if cont["id"] == cid), None)
        if contact:
            def _make_edit(cont=contact):
                def _do(evt):
                    _show_contact_form(supplier_id, cont)
                return _do
            btn.bind("click", _make_edit())

    for btn in document.select(".del-contact-btn"):
        cid = int(btn.getAttribute("data-contact-id"))
        def _make_del(contact_id=cid):
            def _do(evt):
                if not window.confirm("Delete this contact?"):
                    return
                try:
                    api.delete_supplier_contact(supplier_id, contact_id)
                    app.toast("Contact deleted", "success")
                    render_detail(supplier_id)
                except api.ApiError as err:
                    app.toast(f"Error: {err.message}", "error")
            return _do
        btn.bind("click", _make_del())


def _show_contact_form(supplier_id, contact=None):
    form_div = document.getElementById("contact-form")
    if not form_div:
        return
    contact = contact or {}
    is_edit = bool(contact.get("id"))
    cid = contact.get("id", "")

    form_div.html = app.render_partial("tpl-supplier-contact-form", {
        "name": contact.get("name", ""),
        "title": contact.get("title", ""),
        "phone": contact.get("phone", ""),
        "email": contact.get("email", ""),
        "is_primary": bool(contact.get("is_primary")),
    })
    form = document.getElementById("form-sup-contact")
    if form:
        def _submit(evt):
            evt.preventDefault()
            payload = form_data("#form-sup-contact")
            try:
                if is_edit:
                    api.update_supplier_contact(supplier_id, cid, payload)
                else:
                    api.create_supplier_contact(supplier_id, payload)
                app.toast("Contact saved", "success")
                render_detail(supplier_id)
            except api.ApiError as err:
                app.toast(f"Error: {err.message}", "error")
        form.bind("submit", _submit)
    cancel = document.getElementById("btn-cancel-contact")
    if cancel:
        cancel.bind("click", lambda evt: setattr(form_div, "html", ""))


def render_form(supplier=None):
    """Full-page add/edit form for a supplier."""
    is_edit = supplier is not None
    supplier = supplier or {}

    current_terms = supplier.get("terms", "NET30")
    terms = [
        {"value": val, "label": label, "is_selected": current_terms == val}
        for val, label in SUPPLIER_TERMS
    ]
    current_shipping = supplier.get("default_shipping", "ups_ground")
    shipping_methods = [
        {"value": val, "label": label, "is_selected": current_shipping == val}
        for val, label in SHIPPING_METHODS
    ]

    supplier_id = supplier.get("id")
    app.render("tpl-suppliers-form", {
        "title": "Edit Supplier" if is_edit else "Add Supplier",
        "back_href": f"#/suppliers/{supplier_id}" if supplier_id else "#/suppliers",
        "name": supplier.get("name", ""),
        "phone": supplier.get("phone", ""),
        "email": supplier.get("email", ""),
        "website": supplier.get("website", ""),
        "account_number": supplier.get("account_number", ""),
        "notes": supplier.get("notes", ""),
        "terms": terms,
        "shipping_methods": shipping_methods,
    })

    form = document.getElementById("form-supplier")
    if form:
        def _submit(evt):
            evt.preventDefault()
            payload = form_data("#form-supplier")
            try:
                if is_edit:
                    api.update_supplier(supplier_id, payload)
                    app.toast("Supplier updated", "success")
                    render_detail(supplier_id)
                else:
                    result = api.create_supplier(payload)
                    app.toast("Supplier created", "success")
                    render_detail(result["id"])
            except api.ApiError as err:
                app.toast(f"Error: {err.message}", "error")
        form.bind("submit", _submit)
