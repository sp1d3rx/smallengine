"""Reports page — loads data from reports API endpoints and renders analytics dashboards with interactive drill-downs."""
import app
import api
from browser import document

_active_report = "revenue"  # mutable global to track current report view


def render_page(report_name=None):
    """Render the requested report tab, loading statistics from the backend APIs."""
    global _active_report
    if report_name:
        _active_report = report_name

    try:
        revenue_data = []
        techs_data = []
        warranty_data = []
        inv_data = {}

        if _active_report == "revenue":
            raw = api.get("/shop/api/reports/revenue")
            revenue_data = raw.get("revenue", [])
            for r in revenue_data:
                r["total_revenue"] = f"{float(r.get('total_revenue', 0)):,.2f}"
                r["cogs"] = f"{float(r.get('cogs', 0)):,.2f}"
                r["gross_profit"] = f"{float(r.get('gross_profit', 0)):,.2f}"
                r["gross_margin"] = f"{float(r.get('gross_margin', 0)):.1f}"

        elif _active_report == "technicians":
            raw = api.get("/shop/api/reports/technicians")
            techs_data = raw.get("technicians", [])
            for t in techs_data:
                comp = int(t.get("completed", 0))
                hours = float(t.get("hours", 0))
                rev = float(t.get("revenue", 0))

                t["completed"] = str(comp)
                t["hours"] = f"{hours:.2f}"
                t["revenue"] = f"{rev:,.2f}"
                t["avg_hours"] = f"{hours / comp:.2f}" if comp > 0 else "0.00"
                t["avg_revenue"] = f"{rev / comp:,.2f}" if comp > 0 else "0.00"

        elif _active_report == "warranty":
            raw = api.get("/shop/api/reports/warranty")
            warranty_data = raw.get("warranty", [])
            for w in warranty_data:
                sub = float(w.get("total_submitted", 0))
                paid = float(w.get("total_paid", 0))
                w["total_submitted"] = f"{sub:,.2f}"
                w["total_paid"] = f"{paid:,.2f}"
                w["recovery_ratio"] = f"{(paid / sub) * 100:.1f}" if sub > 0 else "0.0"

        elif _active_report == "inventory":
            raw = api.get("/shop/api/reports/inventory")
            inv_raw = raw.get("inventory", {})
            cost = float(inv_raw.get("total_cost_value", 0))
            retail = float(inv_raw.get("total_retail_value", 0))
            margin = float(inv_raw.get("potential_margin", 0))

            inv_data = {
                "total_items": str(inv_raw.get("total_items", 0)),
                "total_qty": str(inv_raw.get("total_qty", 0)),
                "total_cost_value": cost,
                "total_retail_value": retail,
                "potential_margin": margin,
                "total_cost_value_fmt": f"{cost:,.2f}",
                "total_retail_value_fmt": f"{retail:,.2f}",
                "potential_margin_fmt": f"{margin:,.2f}",
                "markup_pct": f"{(margin / cost) * 100:.1f}" if cost > 0 else "0.0",
                "categories": inv_raw.get("categories", []),
            }

    except api.ApiError as err:
        app.toast(f"Error loading report: {err.message}", "error")
        return

    app.render("tpl-reports", {
        "active_report": _active_report,
        "revenue": revenue_data,
        "technicians": techs_data,
        "warranty": warranty_data,
        "inventory": inv_data,
    })

    _bind_events()


def _bind_events():
    """Bind clicks on report selector tabs and drillable elements."""
    btn_revenue = document.getElementById("btn-rep-revenue")
    if btn_revenue:
        btn_revenue.bind("click", lambda ev: render_page("revenue"))

    btn_techs = document.getElementById("btn-rep-techs")
    if btn_techs:
        btn_techs.bind("click", lambda ev: render_page("technicians"))

    btn_warranty = document.getElementById("btn-rep-warranty")
    if btn_warranty:
        btn_warranty.bind("click", lambda ev: render_page("warranty"))

    btn_inventory = document.getElementById("btn-rep-inventory")
    if btn_inventory:
        btn_inventory.bind("click", lambda ev: render_page("inventory"))

    # Drill down: Monthly Revenue
    for tr in document.select(".btn-drill-revenue"):
        month = tr.getAttribute("data-month")
        tr.bind("click", lambda ev, m=month: _drill_revenue(m))

    # Drill down: Technician productivity
    for tr in document.select(".btn-drill-tech"):
        tech_id = tr.getAttribute("data-tech-id")
        name = tr.getAttribute("data-tech-name")
        tr.bind("click", lambda ev, tid=tech_id, n=name: _drill_technician(tid, n))

    # Drill down: Warranty recoveries
    for tr in document.select(".btn-drill-warranty"):
        mfr_id = tr.getAttribute("data-mfr-id")
        name = tr.getAttribute("data-mfr-name")
        tr.bind("click", lambda ev, mid=mfr_id, n=name: _drill_warranty(mid, n))

    # Drill down: Category assets valuation
    for tr in document.select(".btn-drill-inventory"):
        cat_val = tr.getAttribute("data-cat-val")
        label = tr.getAttribute("data-cat-label")
        tr.bind("click", lambda ev, cv=cat_val, l=label: _drill_inventory(cv, l))


def _bind_modal_close():
    """Bind close button within a drill down modal."""
    close_btn = document.getElementById("btn-close-drill")
    if close_btn:
        close_btn.bind("click", lambda ev: app.close_modal())


def _drill_revenue(month):
    """Fetch details for a month's revenue and display in a modal."""
    try:
        data = api.get(f"/shop/api/reports/revenue/{month}")
    except api.ApiError as err:
        app.toast(f"Error loading details: {err.message}", "error")
        return

    details = data.get("details", [])
    for d in details:
        d["revenue"] = f"{float(d.get('revenue', 0)):,.2f}"
        d["cogs"] = f"{float(d.get('cogs', 0)):,.2f}"
        d["gross_profit"] = f"{float(d.get('gross_profit', 0)):,.2f}"

    body_html = app.render_partial("tpl-drill-revenue", {"details": details})
    app.modal(f"Revenue Detail — {month}", body_html, wide=True)
    _bind_modal_close()


def _drill_technician(tech_id, tech_name):
    """Fetch details of jobs completed by a technician and display in a modal."""
    try:
        data = api.get(f"/shop/api/reports/technicians/{tech_id}")
    except api.ApiError as err:
        app.toast(f"Error loading details: {err.message}", "error")
        return

    details = data.get("details", [])
    for d in details:
        d["hours"] = f"{float(d.get('hours', 0)):.2f}"
        d["revenue"] = f"{float(d.get('revenue', 0)):,.2f}"

    body_html = app.render_partial("tpl-drill-tech", {"details": details})
    app.modal(f"Jobs Completed by {tech_name}", body_html, wide=True)
    _bind_modal_close()


def _drill_warranty(mfr_id, mfr_name):
    """Fetch all warranty claims submitted to a manufacturer and display in a modal."""
    try:
        data = api.get(f"/shop/api/reports/warranty/{mfr_id}")
    except api.ApiError as err:
        app.toast(f"Error loading details: {err.message}", "error")
        return

    details = data.get("details", [])
    for d in details:
        d["covered_labor"] = f"{float(d.get('covered_labor', 0)):.2f}"
        d["covered_parts"] = f"{float(d.get('covered_parts', 0)):.2f}"
        d["total_claimed"] = f"{float(d.get('total_claimed', 0)):.2f}"
        d["reimbursement_amount"] = f"{float(d['reimbursement_amount']):.2f}" if d.get("reimbursement_amount") is not None else None

    body_html = app.render_partial("tpl-drill-warranty", {"details": details})
    app.modal(f"Warranty Claims — {mfr_name}", body_html, wide=True)
    _bind_modal_close()


def _drill_inventory(cat_val, cat_label):
    """Fetch parts belonging to a compatibility category and display valuation details in a modal."""
    try:
        data = api.get(f"/shop/api/reports/inventory/category/{cat_val}")
    except api.ApiError as err:
        app.toast(f"Error loading details: {err.message}", "error")
        return

    parts = data.get("parts", [])
    body_html = app.render_partial("tpl-drill-inventory", {"parts": parts})
    app.modal(f"Valuation Detail — {cat_label} Compatibility", body_html, wide=True)
    _bind_modal_close()
