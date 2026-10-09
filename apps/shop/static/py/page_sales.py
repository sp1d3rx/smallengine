"""Sales list page — retail and equipment sales with date filtering and ID lookup."""
import app
import api
from browser import document, window

_PAYMENT_LABELS = {
    "cash": "Cash", "card": "Card", "check": "Check", "warranty": "Warranty",
}

_current_days = ["2"]   # mutable so inner functions can update it


def _fmt(val):
    try:
        return f"${float(val):.2f}"
    except Exception:
        return "$0.00"


def render_list(days=None):
    if days is not None:
        _current_days[0] = str(days)
    _load(_current_days[0])


def _load(days, sale_id=None):
    _current_days[0] = str(days)
    try:
        if sale_id:
            data = api.get("/shop/api/sales", {"id": sale_id})
        else:
            data = api.get("/shop/api/sales", {"days": days})
    except api.ApiError as err:
        app.toast(f"Error loading sales: {err.message}", "error")
        return

    rows = []
    for s in data.get("sales", []):
        status = s.get("status") or ""
        # is_retail: sale_line-driven retail sales have no equipment_id
        is_retail = not s.get("equipment_id")
        cust_first = s.get("customer_first") or ""
        cust_last = s.get("customer_last") or ""
        if cust_first or cust_last:
            customer_name = f"{cust_first} {cust_last}".strip()
        elif s.get("cash_customer_name"):
            customer_name = s["cash_customer_name"]
        else:
            customer_name = "Walk-in"

        rows.append({
            "id": s["id"],
            "sale_date": str(s.get("sale_date", ""))[:10],
            "type_label": "Retail" if is_retail else "Equipment",
            "is_retail": is_retail,
            "is_paid": is_retail and status == "paid",
            "customer_name": customer_name,
            "total_fmt": _fmt(s.get("total", 0)),
            "payment_label": _PAYMENT_LABELS.get(s.get("payment_method", ""), s.get("payment_method", "") or "—"),
            "status": status or "—",
        })

    app.render("tpl-sales-list", {"sales": rows, "days": str(days)})
    _bind(days)


def _bind(days):
    # Date-range buttons
    for btn in document.select("[data-days]"):
        d = btn.getAttribute("data-days")
        def _click(ev, dv=d):
            ev.preventDefault()
            _load(dv)
        btn.bind("click", _click)

    # Sale ID search
    search_el = document.getElementById("sale-id-search")
    if search_el:
        def _on_search(ev):
            val = ev.target.value.strip()
            if val.isdigit():
                _load(days, sale_id=val)
            elif not val:
                _load(_current_days[0])
        search_el.bind("input", _on_search)

        def _on_keydown(ev):
            if ev.key == "Escape":
                search_el.value = ""
                _load(_current_days[0])
        search_el.bind("keydown", _on_keydown)
