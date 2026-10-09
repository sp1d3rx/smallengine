"""Warranty hub page — claims tracking, claim submissions, and manufacturers management."""
import app
import api
from browser import document, window

_active_tab = "claims"  # mutable global for tracking selected tab


def render_list(tab=None):
    """Render the warranty page, displaying either claims, eligible work orders, or manufacturers."""
    global _active_tab
    if tab:
        _active_tab = tab

    try:
        claims_data = api.get("/shop/api/warranty")
        eligible_data = api.get("/shop/api/warranty/eligible_workorders")
        mfrs_data = api.get("/shop/api/manufacturers")
    except api.ApiError as err:
        app.toast(f"Error loading warranty data: {err.message}", "error")
        return

    claims = claims_data.get("claims", [])
    eligible = eligible_data.get("work_orders", [])
    mfrs = mfrs_data.get("manufacturers", [])

    # Format values for display
    formatted_claims = []
    for c in claims:
        formatted_claims.append({
            "id": c["id"],
            "work_order_id": c["work_order_id"],
            "manufacturer_name": c.get("manufacturer_name", ""),
            "customer_name": c.get("customer_name", ""),
            "equip_desc": c.get("equip_desc", ""),
            "submitted_date": str(c.get("submitted_date", ""))[:10],
            "covered_labor": f"{float(c.get('covered_labor', 0)):.2f}",
            "covered_parts": f"{float(c.get('covered_parts', 0)):.2f}",
            "status": c.get("status", ""),
            "reimbursement_amount": f"{float(c['reimbursement_amount']):.2f}" if c.get("reimbursement_amount") is not None else None,
        })

    formatted_eligible = []
    for e in eligible:
        formatted_eligible.append({
            "id": e["id"],
            "manufacturer_id": e.get("manufacturer_id"),
            "customer_name": e.get("customer_name", ""),
            "equip_desc": e.get("equip_desc", ""),
            "date_in": str(e.get("date_in", ""))[:10],
            "covered_labor": f"{float(e.get('covered_labor', 0)):.2f}",
            "covered_parts": f"{float(e.get('covered_parts', 0)):.2f}",
        })

    app.render("tpl-warranty-list", {
        "active_tab": _active_tab,
        "eligible_count": len(eligible),
        "claims": formatted_claims,
        "eligible": formatted_eligible,
        "manufacturers": mfrs,
    })

    _bind_events()


def _bind_events():
    """Bind tab clicks and action buttons in the list views."""
    # Tab switches
    tab_claims = document.getElementById("tab-claims")
    if tab_claims:
        tab_claims.bind("click", lambda ev: render_list("claims"))

    tab_eligible = document.getElementById("tab-eligible")
    if tab_eligible:
        tab_eligible.bind("click", lambda ev: render_list("eligible"))

    tab_mfrs = document.getElementById("tab-mfrs")
    if tab_mfrs:
        tab_mfrs.bind("click", lambda ev: render_list("mfrs"))

    # Claims actions: View Details
    for btn in document.select(".btn-view-claim"):
        claim_id = btn.getAttribute("data-claim-id")
        btn.bind("click", lambda ev, cid=claim_id: _view_claim_detail(cid))

    # Eligible actions: Submit Claim
    for btn in document.select(".btn-create-claim"):
        wo_id = btn.getAttribute("data-wo-id")
        mfr_id = btn.getAttribute("data-mfr-id")
        labor = btn.getAttribute("data-labor")
        parts = btn.getAttribute("data-parts")
        btn.bind("click", lambda ev, wid=wo_id, mid=mfr_id, l=labor, p=parts: _show_claim_form(wid, mid, l, p))

    # Manufacturer actions: New & Edit
    btn_new_mfr = document.getElementById("btn-new-mfr")
    if btn_new_mfr:
        btn_new_mfr.bind("click", lambda ev: _show_mfr_form())

    for btn in document.select(".btn-edit-mfr"):
        mfr_id = btn.getAttribute("data-mfr-id")
        btn.bind("click", lambda ev, mid=mfr_id: _edit_mfr(mid))


def _view_claim_detail(claim_id):
    """Fetch and display a claim's full details in a modal."""
    try:
        data = api.get(f"/shop/api/warranty/{claim_id}")
    except api.ApiError as err:
        app.toast(f"Error loading claim: {err.message}", "error")
        return

    claim = data.get("claim", {})
    labor = float(claim.get("covered_labor", 0))
    parts = float(claim.get("covered_parts", 0))

    payload = {
        "id": claim["id"],
        "work_order_id": claim["work_order_id"],
        "manufacturer_name": claim.get("manufacturer_name", ""),
        "customer_name": claim.get("customer_name", ""),
        "equip_desc": claim.get("equip_desc", ""),
        "status": claim.get("status", ""),
        "mfr_claim_number": claim.get("mfr_claim_number"),
        "submitted_date": str(claim.get("submitted_date", ""))[:10],
        "payment_date": str(claim.get("payment_date", ""))[:10] if claim.get("payment_date") else None,
        "covered_labor": f"{labor:.2f}",
        "covered_parts": f"{parts:.2f}",
        "total_claimed": f"{labor + parts:.2f}",
        "reimbursement_amount": f"{float(claim['reimbursement_amount']):.2f}" if claim.get("reimbursement_amount") is not None else None,
        "notes": claim.get("notes", ""),
    }

    body_html = app.render_partial("tpl-warranty-claim-detail", payload)
    app.modal("Warranty Claim Details", body_html)

    close_btn = document.getElementById("btn-close-claim-detail")
    if close_btn:
        close_btn.bind("click", lambda ev: app.close_modal())

    pay_form = document.getElementById("form-claim-payment")
    if pay_form:
        pay_form.bind("submit", lambda ev: _submit_claim_payment(ev, claim_id))


def _submit_claim_payment(event, claim_id):
    """Submit the reimbursement recording form."""
    event.preventDefault()
    form = document.getElementById("form-claim-payment")
    amount = form.select("[name=amount]")[0].value

    try:
        api.post(f"/shop/api/warranty/{claim_id}/payment", {"amount": amount})
        app.toast("Claim payment recorded successfully", "success")
        app.close_modal()
        render_list("claims")
    except api.ApiError as err:
        app.toast(f"Error saving payment: {err.message}", "error")


def _show_claim_form(wo_id, prefilled_mfr_id, labor, parts):
    """Display the claim submission form in a modal."""
    try:
        mfrs_data = api.get("/shop/api/manufacturers")
    except api.ApiError as err:
        app.toast(f"Error loading manufacturers: {err.message}", "error")
        return

    mfrs = mfrs_data.get("manufacturers", [])
    mfrs_options = []
    for m in mfrs:
        mfrs_options.append({
            "id": m["id"],
            "name": m["name"],
            "is_selected": str(m["id"]) == str(prefilled_mfr_id)
        })

    body_html = app.render_partial("tpl-warranty-claim-form", {
        "wo_id": wo_id,
        "manufacturers": mfrs_options,
        "covered_labor": labor,
        "covered_parts": parts,
    })
    app.modal("Submit Warranty Claim", body_html)

    form = document.getElementById("form-submit-warranty")
    if form:
        form.bind("submit", _submit_claim_form)

    cancel_btn = document.getElementById("btn-cancel-claim-submit")
    if cancel_btn:
        cancel_btn.bind("click", lambda ev: app.close_modal())


def _submit_claim_form(event):
    """Create a new warranty claim via the API."""
    event.preventDefault()
    form = document.getElementById("form-submit-warranty")

    def val(name):
        return form.select(f"[name={name}]")[0].value

    data = {
        "work_order_id": int(val("work_order_id")),
        "manufacturer_id": int(val("manufacturer_id")),
        "mfr_claim_number": val("mfr_claim_number").strip(),
        "covered_labor": val("covered_labor"),
        "covered_parts": val("covered_parts"),
    }

    try:
        api.post("/shop/api/warranty", data)
        app.toast("Warranty claim submitted", "success")
        app.close_modal()
        render_list("claims")
    except api.ApiError as err:
        app.toast(f"Error submitting claim: {err.message}", "error")


def _show_mfr_form(mfr_id=None, prefill=None):
    """Show the form to add or edit a manufacturer."""
    prefill = prefill or {}
    is_edit = mfr_id is not None
    action_label = "Update Partner" if is_edit else "Add Partner"

    body_html = app.render_partial("tpl-manufacturer-form", {
        "name": prefill.get("name", ""),
        "contact_name": prefill.get("contact_name", ""),
        "dealer_id": prefill.get("dealer_id", ""),
        "phone": prefill.get("phone", ""),
        "email": prefill.get("email", ""),
        "warranty_notes": prefill.get("warranty_notes", ""),
        "flat_rate_labor": bool(prefill.get("flat_rate_labor", False)),
        "action_label": action_label,
    })
    app.modal(action_label, body_html)

    form = document.getElementById("form-manufacturer")
    if form:
        form.bind("submit", lambda ev: _submit_mfr_form(ev, mfr_id))

    cancel_btn = document.getElementById("btn-cancel-mfr")
    if cancel_btn:
        cancel_btn.bind("click", lambda ev: app.close_modal())


def _submit_mfr_form(event, mfr_id=None):
    """Submit the manufacturer form to create or edit."""
    event.preventDefault()
    form = document.getElementById("form-manufacturer")

    def val(name):
        return form.select(f"[name={name}]")[0].value

    flat_checked = form.select("[name=flat_rate_labor]")[0].checked

    data = {
        "name": val("name").strip(),
        "contact_name": val("contact_name").strip(),
        "dealer_id": val("dealer_id").strip(),
        "phone": val("phone").strip(),
        "email": val("email").strip(),
        "warranty_notes": val("warranty_notes").strip(),
        "flat_rate_labor": flat_checked,
    }

    try:
        if mfr_id:
            api.put(f"/shop/api/manufacturers/{mfr_id}", data)
            app.toast("Manufacturer updated", "success")
        else:
            api.post("/shop/api/manufacturers", data)
            app.toast("Manufacturer added", "success")
        app.close_modal()
        render_list("mfrs")
    except api.ApiError as err:
        app.toast(f"Error saving manufacturer: {err.message}", "error")


def _edit_mfr(mfr_id):
    """Retrieve manufacturer details and open edit modal."""
    try:
        data = api.get(f"/shop/api/manufacturers/{mfr_id}")
        _show_mfr_form(mfr_id=mfr_id, prefill=data.get("manufacturer", {}))
    except api.ApiError as err:
        app.toast(f"Error: {err.message}", "error")
