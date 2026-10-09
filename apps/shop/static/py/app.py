"""Gantrika App Shell — Core SPA router, UI helpers, and page dispatcher."""
from browser import document, window
import gantrika
from gantrika import (
    router, route, Toast, Modal, render, render_partial,
    form_data, populate_form, set_form_errors, clear_form_errors,
    Resource, ApiError
)

# ── App-level config ──────────────────────────────────────────────────────────
IS_ADMIN = bool(window.APP_IS_ADMIN)

# ── Backwards-compatible helper aliases for page modules ───────────────────────
def toast(message, kind="info", duration=4000):
    Toast.show(message, kind, duration)

def modal(title, body_html, wide=False):
    return Modal.show(title, body_html, wide=wide)

def close_modal():
    Modal.close()


# ── Declarative Routes ─────────────────────────────────────────────────────────

@route("")
@route("/")
@route("/dashboard")
def _dashboard():
    import page_dashboard
    page_dashboard.render_page()


@route("/customers")
def _customers_list():
    import page_customers
    page_customers.render_list()


@route("/customers/<id:int>")
def _customers_detail(id):
    import page_customers
    page_customers.render_detail(id)


@route("/workorders/new")
def _workorders_new():
    import page_work_orders
    query = router.current_query
    cid = int(query["customer_id"]) if query.get("customer_id") else None
    eid = int(query["equipment_id"]) if query.get("equipment_id") else None
    page_work_orders.render_intake(prefill_customer_id=cid, prefill_equipment_id=eid)


@route("/workorders/<id:int>/invoice")
def _workorders_invoice(id):
    import page_work_order_detail
    page_work_order_detail.render_invoice(id)


@route("/workorders/<id:int>/intake-doc")
def _workorders_intake_doc(id):
    import page_work_order_detail
    page_work_order_detail.render_intake_doc(id)


@route("/workorders/<id:int>")
def _workorders_detail(id):
    import page_work_order_detail
    page_work_order_detail.render_detail(id)


@route("/workorders")
def _workorders_list():
    import page_work_orders
    page_work_orders.render_list()


@route("/reception")
def _reception():
    import page_reception
    page_reception.render_page()


@route("/warranty")
def _warranty():
    import page_warranty
    page_warranty.render_list()


@route("/parts")
def _parts_list():
    import page_parts
    low_stock = router.current_query.get("low_stock") == "1"
    page_parts.render_list(low_stock=low_stock)


@route("/parts/<id:int>")
def _parts_detail(id):
    import page_parts
    page_parts.render_detail(id)


@route("/suppliers")
def _suppliers_list():
    if not IS_ADMIN:
        document["content"].html = "<section class='page'><p class='muted'>Access denied.</p></section>"
    else:
        import page_suppliers
        page_suppliers.render_list()


@route("/suppliers/<id:int>")
def _suppliers_detail(id):
    if not IS_ADMIN:
        document["content"].html = "<section class='page'><p class='muted'>Access denied.</p></section>"
    else:
        import page_suppliers
        page_suppliers.render_detail(id)


@route("/purchasing/new")
def _purchasing_new():
    if not IS_ADMIN:
        document["content"].html = "<section class='page'><p class='muted'>Access denied.</p></section>"
    else:
        import page_purchase_orders
        query = router.current_query
        sid = int(query["supplier_id"]) if query.get("supplier_id") else None
        pid = int(query["part_id"]) if query.get("part_id") else None
        page_purchase_orders.render_new_po(prefill_supplier_id=sid, prefill_part_id=pid)


@route("/purchasing/<id:int>")
def _purchasing_detail(id):
    if not IS_ADMIN:
        document["content"].html = "<section class='page'><p class='muted'>Access denied.</p></section>"
    else:
        import page_purchase_orders
        page_purchase_orders.render_detail(id)


@route("/purchasing")
def _purchasing_list():
    if not IS_ADMIN:
        document["content"].html = "<section class='page'><p class='muted'>Access denied.</p></section>"
    else:
        import page_purchase_orders
        page_purchase_orders.render_list()


@route("/retail/new")
def _retail_new():
    import page_retail
    page_retail.render_new_sale()


@route("/retail/<id:int>")
def _retail_pos(id):
    import page_retail
    page_retail.render_pos(id)


@route("/retail")
def _retail_default():
    import page_retail
    page_retail.render_new_sale()


@route("/sales")
def _sales():
    import page_sales
    page_sales.render_list()


@route("/reports/<report_name:str>")
def _reports_sub(report_name):
    import page_reports
    page_reports.render_page(report_name)


@route("/reports")
def _reports_default():
    import page_reports
    page_reports.render_page()


@route("/settings")
def _settings():
    import page_settings
    page_settings.render_page()


# ── App Boot ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    router.start()
