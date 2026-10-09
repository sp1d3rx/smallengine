"""Settings page — shop config and user management (admin only)."""
import app
import api
from gantrika import form_data
from browser import document, window


def render_page():
    """Render settings; redirect to dashboard if not admin."""
    current_user = window.__shop_user
    if not current_user.is_admin:
        window.location.hash = "#/"
        return

    try:
        settings_data = api.get("/shop/api/settings")
        users_data = api.get("/shop/api/users")
    except api.ApiError as err:
        app.toast(f"Error loading settings: {err.message}", "error")
        return

    settings = settings_data.get("settings", {})
    users = users_data.get("users", [])

    user_rows = []
    for usr in users:
        role = usr.get("role", "none")
        badge_cls = "badge-ready" if role == "admin" else "badge-diagnosed" if role == "tech" else "badge-neutral"
        user_rows.append({
            "id": usr["id"],
            "name": f"{usr.get('first_name','')} {usr.get('last_name','')}",
            "email": usr.get("email", ""),
            "role": role,
            "badge_cls": badge_cls,
        })

    app.render("tpl-settings", {
        "shop_name": settings.get("shop_name", ""),
        "phone": settings.get("phone", ""),
        "email": settings.get("email", ""),
        "address": settings.get("address", ""),
        "city": settings.get("city", ""),
        "zip_code": settings.get("zip_code", ""),
        "tax_rate": settings.get("tax_rate", 0.0825),
        "default_labor_rate": settings.get("default_labor_rate", 85),
        "estimate_approval_threshold": settings.get("estimate_approval_threshold", 100),
        "intake_disclaimer": settings.get("intake_disclaimer", ""),
        "users": user_rows,
    })

    _bind_events()


def _bind_events():
    form = document.getElementById("form-shop-settings")
    if form:
        form.bind("submit", _save_settings)

    btn = document.getElementById("btn-new-user")
    if btn:
        btn.bind("click", lambda evt: _show_user_form())

    window.editUser = _edit_user
    window.deleteUser = _delete_user


def _save_settings(event):
    event.preventDefault()
    data = form_data("#form-shop-settings")
    try:
        api.put("/shop/api/settings", data)
        app.toast("Settings saved", "success")
    except api.ApiError as err:
        app.toast(f"Error: {err.message}", "error")


def _show_user_form(user_id=None, prefill=None):
    prefill = prefill or {}
    is_edit = user_id is not None
    action_label = "Update User" if is_edit else "Create User"

    current_role = prefill.get("role", "tech")
    roles = [
        {"value": val, "label": lbl, "is_selected": current_role == val}
        for val, lbl in [("tech", "Tech"), ("receptionist", "Receptionist"), ("admin", "Admin")]
    ]

    body_html = app.render_partial("tpl-user-form", {
        "first_name": prefill.get("first_name", ""),
        "last_name": prefill.get("last_name", ""),
        "email": prefill.get("email", ""),
        "is_edit": is_edit,
        "roles": roles,
        "action_label": action_label,
    })
    app.modal(action_label, body_html)

    form_el = document.getElementById("form-user")
    if form_el:
        form_el.bind("submit", lambda evt: _submit_user_form(evt, user_id))

    cancel_btn = document.getElementById("btn-cancel-user")
    if cancel_btn:
        cancel_btn.bind("click", lambda evt: app.close_modal())


def _submit_user_form(event, user_id=None):
    event.preventDefault()
    data = form_data("#form-user")
    if not data.get("role"):
        data["role"] = "tech"

    try:
        if user_id:
            api.put(f"/shop/api/users/{user_id}", data)
            app.toast("User updated", "success")
        else:
            api.post("/shop/api/users", data)
            app.toast("User created", "success")
        app.close_modal()
        render_page()
    except api.ApiError as err:
        app.toast(f"Error: {err.message}", "error")


def _edit_user(user_id):
    try:
        data = api.get(f"/shop/api/users/{user_id}")
        _show_user_form(user_id=user_id, prefill=data.get("user", {}))
    except api.ApiError as err:
        app.toast(f"Error: {err.message}", "error")


def _delete_user(user_id):
    if not window.confirm("Delete this user?"):
        return
    try:
        api.delete(f"/shop/api/users/{user_id}")
        app.toast("User deleted", "success")
        render_page()
    except api.ApiError as err:
        app.toast(f"Error: {err.message}", "error")
