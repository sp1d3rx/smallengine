"""Retail / point-of-sale page."""
import app
import api
from browser import document, window

_search_timer = [None]
_checkout_customer = {"id": None}


def _fmt(val):
    try:
        return f"${float(val):.2f}"
    except Exception:
        return "$0.00"


def _build_pos_ctx(sale, lines):
    line_data = []
    for ln in lines:
        line_data.append({
            "id": ln["id"],
            "description": ln.get("description", ""),
            "quantity": ln.get("quantity", 1),
            "unit_price_fmt": _fmt(ln.get("unit_price", 0)),
            "total_fmt": _fmt(ln.get("total", 0)),
        })
    return {
        "sale_id": sale["id"],
        "subtotal_fmt": _fmt(sale.get("subtotal", 0)),
        "tax_fmt": _fmt(sale.get("tax_amount", 0)),
        "total_fmt": _fmt(sale.get("total", 0)),
        "lines": line_data,
        "has_lines": len(line_data) > 0,
    }


# ── Entry points ──────────────────────────────────────────────────────────────

def render_new_sale():
    """Create a new open sale and redirect to its POS page."""
    try:
        result = api.create_retail_sale()
    except api.ApiError as err:
        app.toast(f"Could not start sale: {err.message}", "error")
        return
    sale_id = result.get("id")
    window.location.hash = f"#/retail/{sale_id}"


def render_pos(sale_id):
    """Fetch sale and render the appropriate view (open / paid / voided)."""
    try:
        sale_response = api.get_retail_sale(sale_id)
    except api.ApiError as err:
        app.toast(f"Error loading sale: {err.message}", "error")
        return

    sale = sale_response.get("sale", {})
    lines = sale_response.get("lines", [])
    customer = sale_response.get("customer")
    status = sale.get("status", "open")

    if status == "open":
        ctx = _build_pos_ctx(sale, lines)
        app.render("tpl-retail-pos", ctx)
        _bind_pos(sale_id)
    elif status == "paid":
        _render_receipt(sale_id, sale, lines, customer)
    else:
        app.render("tpl-retail-voided", {"sale_id": sale_id})


# ── Receipt view ──────────────────────────────────────────────────────────────

def _render_receipt(sale_id, sale, lines, customer):
    try:
        settings_data = api.get_settings()
        settings = settings_data.get("settings", {})
    except api.ApiError:
        settings = {}

    shop_name = settings.get("shop_name", "")
    addr = settings.get("address", "")
    city = settings.get("city", "")
    state = settings.get("state", "")
    zip_code = settings.get("zip_code", "")
    city_state_zip = ", ".join(p for p in [city, state, zip_code] if p)
    shop_addr_line = f"{addr}, {city_state_zip}".strip(", ") if addr else city_state_zip

    payment_labels = {"cash": "Cash", "card": "Card", "check": "Check", "warranty": "Warranty"}
    payment_method = sale.get("payment_method", "")

    customer_name = ""
    if customer:
        customer_name = f"{customer.get('first_name','')} {customer.get('last_name','')}".strip()
    elif sale.get("cash_customer_name"):
        customer_name = sale["cash_customer_name"]

    line_data = []
    for ln in lines:
        line_data.append({
            "id": ln.get("id"),
            "description": ln.get("description", ""),
            "quantity": ln.get("quantity", 1),
            "unit_price_fmt": _fmt(ln.get("unit_price", 0)),
            "total_fmt": _fmt(ln.get("total", 0)),
        })

    ctx = {
        "sale_id": sale_id,
        "shop_name": shop_name,
        "shop_addr_line": shop_addr_line,
        "shop_phone": settings.get("phone", ""),
        "sale_date": str(sale.get("sale_date", ""))[:10],
        "payment_method_label": payment_labels.get(payment_method, payment_method),
        "payment_reference": sale.get("payment_reference", ""),
        "customer_name": customer_name,
        "lines": line_data,
        "subtotal_fmt": _fmt(sale.get("subtotal", 0)),
        "tax_fmt": _fmt(sale.get("tax_amount", 0)),
        "total_fmt": _fmt(sale.get("total", 0)),
        "can_void": True,
    }
    app.render("tpl-retail-receipt", ctx)

    void_btn = document.getElementById("btn-void-sale")
    if void_btn:
        def _void(ev, sid=sale_id):
            if window.confirm("Void entire sale and restock all parts?"):
                try:
                    api.void_retail_sale(sid)
                    render_pos(sid)
                except api.ApiError as err:
                    app.toast(f"Void failed: {err.message}", "error")
        void_btn.bind("click", _void)

    return_btn = document.getElementById("btn-return-items")
    if return_btn:
        def _open_return(ev, sid=sale_id, ln=line_data):
            body_html = app.render_partial("tpl-retail-return", {"lines": ln})
            app.modal("Return Items — Sale #" + str(sid), body_html)

            cancel_btn = document.getElementById("btn-cancel-return")
            if cancel_btn:
                cancel_btn.bind("click", lambda ev: app.close_modal())

            form = document.getElementById("form-return")
            if form:
                def _submit_return(ev, sid2=sid):
                    ev.preventDefault()
                    items = []
                    for inp in document.select(".return-qty-input"):
                        qty = int(inp.value or 0)
                        if qty > 0:
                            lid = int(inp.getAttribute("data-line-id"))
                            items.append({"line_id": lid, "quantity": qty})
                    if not items:
                        app.toast("No quantities entered.", "error")
                        return
                    try:
                        result = api.return_retail_sale(sid2, items)
                        app.close_modal()
                        if result.get("voided"):
                            app.toast("Return complete — sale voided.", "success")
                        else:
                            app.toast("Partial return processed.", "success")
                        render_pos(sid2)
                    except api.ApiError as err:
                        app.toast(f"Return failed: {err.message}", "error")
                form.bind("submit", _submit_return)

        return_btn.bind("click", _open_return)


# ── Cart reload (partial refresh) ─────────────────────────────────────────────

def _reload_cart(sale_id):
    try:
        sale_response = api.get_retail_sale(sale_id)
    except api.ApiError as err:
        app.toast(f"Error: {err.message}", "error")
        return

    sale = sale_response.get("sale", {})
    lines = sale_response.get("lines", [])
    ctx = _build_pos_ctx(sale, lines)

    cart_el = document.getElementById("pos-cart")
    if cart_el:
        cart_el.html = app.render_partial("tpl-retail-cart", ctx)

    sub_el = document.getElementById("pos-subtotal")
    tax_el = document.getElementById("pos-tax")
    tot_el = document.getElementById("pos-total")
    if sub_el:
        sub_el.html = ctx["subtotal_fmt"]
    if tax_el:
        tax_el.html = ctx["tax_fmt"]
    if tot_el:
        tot_el.html = ctx["total_fmt"]

    checkout_btn = document.getElementById("btn-checkout")
    if checkout_btn:
        if ctx["has_lines"]:
            checkout_btn.removeAttribute("disabled")
        else:
            checkout_btn.setAttribute("disabled", "disabled")

    _bind_remove_buttons(sale_id)


# ── Event bindings ─────────────────────────────────────────────────────────────

def _bind_remove_buttons(sale_id):
    for btn in document.select(".btn-remove-line"):
        line_id = int(btn.getAttribute("data-line-id"))
        def _remove(ev, sid=sale_id, lid=line_id):
            ev.preventDefault()
            try:
                api.remove_retail_line(sid, lid)
                _reload_cart(sid)
            except api.ApiError as err:
                app.toast(f"Error: {err.message}", "error")
        btn.bind("click", _remove)


def _bind_add_buttons(sale_id):
    for btn in document.select(".btn-pos-add"):
        part_id = int(btn.getAttribute("data-part-id"))
        def _add(ev, sid=sale_id, pid=part_id):
            ev.preventDefault()
            try:
                api.add_retail_line(sid, pid)
                _reload_cart(sid)
                app.toast("Added to cart", "info", 1500)
            except api.ApiError as err:
                app.toast(f"Error: {err.message}", "error")
        btn.bind("click", _add)


def _bind_pos(sale_id):
    _checkout_customer["id"] = None

    # Part search with debounce
    search_el = document.getElementById("pos-search")
    if search_el:
        search_el.focus()
        def _on_search(ev):
            query = ev.target.value.strip()
            if _search_timer[0]:
                window.clearTimeout(_search_timer[0])

            def _do_search(query=query, sid=sale_id):
                results_el = document.getElementById("pos-results")
                if not query:
                    if results_el:
                        results_el.html = ""
                    return
                try:
                    search_response = api.search_retail_parts(query)
                except api.ApiError:
                    return
                parts = search_response.get("parts", [])
                part_rows = []
                for part in parts:
                    part_rows.append({
                        "id": part["id"],
                        "description": part.get("description", ""),
                        "part_number": part.get("part_number", ""),
                        "qty_on_hand": part.get("qty_on_hand", 0),
                        "in_stock": (part.get("qty_on_hand") or 0) > 0,
                        "price_fmt": _fmt(part.get("price", 0)),
                    })
                if results_el:
                    results_el.html = app.render_partial(
                        "tpl-retail-part-results", {"parts": part_rows}
                    )
                _bind_add_buttons(sid)

            _search_timer[0] = window.setTimeout(_do_search, 300)

        search_el.bind("input", _on_search)

    # Void button
    void_btn = document.getElementById("btn-void-sale")
    if void_btn:
        def _void(ev, sid=sale_id):
            if window.confirm("Void this sale?"):
                try:
                    api.void_retail_sale(sid)
                    render_pos(sid)
                except api.ApiError as err:
                    app.toast(f"Void failed: {err.message}", "error")
        void_btn.bind("click", _void)

    # Checkout button
    checkout_btn = document.getElementById("btn-checkout")
    if checkout_btn:
        def _checkout(ev, sid=sale_id):
            ev.preventDefault()
            _open_checkout_modal(sid)
        checkout_btn.bind("click", _checkout)

    _bind_remove_buttons(sale_id)


# ── Checkout modal ─────────────────────────────────────────────────────────────

def _open_checkout_modal(sale_id):
    try:
        sale_response = api.get_retail_sale(sale_id)
    except api.ApiError as err:
        app.toast(f"Error: {err.message}", "error")
        return

    sale = sale_response.get("sale", {})
    total_raw = float(sale.get("total", 0))
    body_html = app.render_partial(
        "tpl-retail-checkout", {"total_fmt": _fmt(total_raw)}
    )
    app.modal("Checkout", body_html)

    # Payment method toggle — show/hide cash tender fields and change display
    def _update_cash_fields():
        pay_el = document.getElementById("checkout-payment-method")
        tender_el = document.getElementById("cash-tender-fields")
        if not pay_el or not tender_el:
            return
        if pay_el.value == "cash":
            tender_el.classList.remove("hidden")
        else:
            tender_el.classList.add("hidden")
            change_el = document.getElementById("cash-change")
            if change_el:
                change_el.text = "—"
                change_el.classList.remove("text-success")
                change_el.classList.remove("text-danger")

    pay_select = document.getElementById("checkout-payment-method")
    if pay_select:
        pay_select.bind("change", lambda ev: _update_cash_fields())

    # Cash tendered → calculate change
    tendered_el = document.getElementById("cash-tendered")
    if tendered_el:
        def _calc_change(ev, total=total_raw):
            change_el = document.getElementById("cash-change")
            if not change_el:
                return
            try:
                given = float(ev.target.value or 0)
                change = given - total
                change_el.classList.remove("text-success")
                change_el.classList.remove("text-danger")
                if given <= 0:
                    change_el.text = "—"
                elif change < 0:
                    change_el.text = f"-{_fmt(abs(change))}"
                    change_el.classList.add("text-danger")
                else:
                    change_el.text = _fmt(change)
                    change_el.classList.add("text-success")
            except Exception:
                change_el.text = "—"
        tendered_el.bind("input", _calc_change)
        tendered_el.focus()

    # Customer type toggle
    for radio in [document.getElementById("cust-type-walkin"), document.getElementById("cust-type-known")]:
        def _toggle(ev):
            walkin_el = document.getElementById("walkin-fields")
            known_el = document.getElementById("known-fields")
            if ev.target.value == "known":
                if walkin_el:
                    walkin_el.classList.add("hidden")
                if known_el:
                    known_el.classList.remove("hidden")
            else:
                if walkin_el:
                    walkin_el.classList.remove("hidden")
                if known_el:
                    known_el.classList.add("hidden")
                _checkout_customer["id"] = None
        radio.bind("change", _toggle)

    # Customer search
    cust_search_el = document.getElementById("checkout-cust-search")
    if cust_search_el:
        def _on_cust_search(ev):
            query = ev.target.value.strip()
            results_el = document.getElementById("checkout-cust-results")
            if len(query) < 2:
                if results_el:
                    results_el.classList.add("hidden")
                return
            try:
                cust_data = api.list_customers(query)
            except api.ApiError:
                return
            customers = cust_data.get("customers", [])
            if not results_el:
                return
            cust_rows = []
            for cust in customers[:8]:
                name = f"{cust.get('first_name','')} {cust.get('last_name','')}".strip()
                phone = cust.get("phone", "")
                display = f"{name} — {phone}" if phone else name
                cust_rows.append({"id": cust["id"], "name": name, "display": display})
            results_el.html = app.render_partial("tpl-retail-cust-results", {"customers": cust_rows})
            results_el.classList.remove("hidden")
            for item in results_el.select(".dropdown-item[data-cust-id]"):
                cust_id = item.getAttribute("data-cust-id")
                cust_name = item.getAttribute("data-cust-name")
                def _select(ev, cid=cust_id, cname=cust_name):
                    _checkout_customer["id"] = int(cid)
                    hidden_el = document.getElementById("checkout-customer-id")
                    if hidden_el:
                        hidden_el.value = cid
                    selected_el = document.getElementById("checkout-cust-selected")
                    if selected_el:
                        selected_el.text = cname
                        selected_el.classList.remove("hidden")
                    cust_results_el = document.getElementById("checkout-cust-results")
                    if cust_results_el:
                        cust_results_el.classList.add("hidden")
                    cust_search_input = document.getElementById("checkout-cust-search")
                    if cust_search_input:
                        cust_search_input.value = cname
                item.bind("click", _select)

        cust_search_el.bind("input", _on_cust_search)

        def _on_blur(ev):
            def _hide():
                cust_results_el = document.getElementById("checkout-cust-results")
                if cust_results_el:
                    cust_results_el.classList.add("hidden")
            window.setTimeout(_hide, 150)
        cust_search_el.bind("blur", _on_blur)

    # Cancel
    cancel_btn = document.getElementById("btn-cancel-checkout")
    if cancel_btn:
        cancel_btn.bind("click", lambda ev: app.close_modal())

    # Form submit
    checkout_form = document.getElementById("form-checkout")
    if checkout_form:
        def _submit(ev, sid=sale_id, total=total_raw):
            ev.preventDefault()
            cust_type = "walkin"
            for radio in [document.getElementById("cust-type-walkin"), document.getElementById("cust-type-known")]:
                if radio.checked:
                    cust_type = radio.value
                    break

            pay_el = document.getElementById("checkout-payment-method")
            ref_el = document.getElementById("checkout-payment-reference")
            name_el = document.getElementById("checkout-cash-customer-name")
            tendered_el = document.getElementById("cash-tendered")

            method = pay_el.value if pay_el else "cash"

            if method == "cash" and tendered_el:
                try:
                    given = float(tendered_el.value or 0)
                except Exception:
                    given = 0
                if given < total:
                    app.toast("Amount given is less than the total.", "error")
                    return

            payload = {
                "payment_method": method,
                "payment_reference": ref_el.value.strip() if ref_el else "",
            }
            if cust_type == "known" and _checkout_customer["id"]:
                payload["customer_id"] = _checkout_customer["id"]
            elif cust_type == "walkin" and name_el:
                payload["cash_customer_name"] = name_el.value.strip()

            try:
                api.pay_retail_sale(sid, payload)
                app.close_modal()
                render_pos(sid)
                app.toast("Sale complete!", "success")
            except api.ApiError as err:
                app.toast(f"Payment failed: {err.message}", "error")

        checkout_form.bind("submit", _submit)
