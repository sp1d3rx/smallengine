"""Dashboard page — role-aware morning view with status counts, overdue WOs, low-stock alert."""
import app
import api
from browser import window
from datetime import date


def render_page():
    current_user = window.__shop_user
    role = str(current_user.role) if hasattr(current_user, "role") else "none"

    status_labels = [
        ("intake",            "Intake"),
        ("diagnosed",         "Diagnosed"),
        ("awaiting_approval", "Awaiting Approval"),
        ("awaiting_parts",    "Awaiting Parts"),
        ("in_repair",         "In Repair"),
        ("ready",             "Ready for Pickup"),
    ]

    try:
        wo_data = api.list_work_orders(status="intake,diagnosed,awaiting_approval,awaiting_parts,in_repair,ready,closed")
        part_data = api.list_parts(low_stock=True)
    except api.ApiError as err:
        app.toast(f"Failed to load dashboard: {err.message}", "error")
        return

    work_orders = wo_data.get("work_orders", [])

    counts = {key: 0 for key, _ in status_labels}
    for wo in work_orders:
        status = wo.get("status", "")
        if status in counts:
            counts[status] += 1

    status_counts = [
        {"label": lbl, "count": counts[key], "status": key}
        for key, lbl in status_labels
    ]

    today = str(date.today())
    overdue = []
    for wo in work_orders:
        promised = wo.get("date_promised", "")
        wo_status = wo.get("status", "")
        if promised and promised < today and wo_status not in ("closed", "cancelled"):
            cust = wo.get("customer") or {}
            equip = wo.get("equipment") or {}
            overdue.append({
                "id": wo["id"],
                "customer_name": f"{cust.get('first_name','')} {cust.get('last_name','')}",
                "equip_desc": f"{equip.get('make','')} {equip.get('model','')}".strip() or "—",
                "date_promised": promised,
                "status": wo_status,
                "status_label": wo_status.replace("_", " ").title(),
            })

    unnotified = []
    for wo in work_orders:
        if wo.get("status") == "ready" and not wo.get("customer_notified_at"):
            cust = wo.get("customer") or {}
            equip = wo.get("equipment") or {}
            contact_pref = (cust.get("contact_preference") or "call").title()
            contact_val = cust.get("phone") or cust.get("email") or "—"
            unnotified.append({
                "id": wo["id"],
                "customer_name": f"{cust.get('first_name','')} {cust.get('last_name','')}",
                "contact_info": f"{contact_pref}: {contact_val}",
                "equip_desc": f"{equip.get('make','')} {equip.get('model','')}".strip() or "—",
            })

    awaiting_pickup = []
    for wo in work_orders:
        if wo.get("status") == "closed" and not wo.get("date_out"):
            cust = wo.get("customer") or {}
            equip = wo.get("equipment") or {}
            ref_str = str(wo.get("modified_on") or wo.get("date_in") or "")[:10]
            try:
                days = (date.today() - date.fromisoformat(ref_str)).days if ref_str else 0
            except Exception:
                days = 0
            awaiting_pickup.append({
                "id": wo["id"],
                "customer_name": f"{cust.get('first_name','')} {cust.get('last_name','')}",
                "equip_desc": f"{equip.get('make','')} {equip.get('model','')}".strip() or "—",
                "days_waiting": days,
                "overdue_pickup": days >= 30,
            })

    low_stock_parts = []
    for part in part_data.get("parts", []):
        low_stock_parts.append({
            "id": part["id"],
            "part_number": part.get("part_number", ""),
            "description": part.get("description", ""),
            "qty_on_hand": part.get("qty_on_hand", 0),
        })

    app.render("tpl-dashboard", {
        "status_counts": status_counts,
        "overdue": overdue,
        "unnotified": unnotified,
        "unnotified_count": len(unnotified),
        "awaiting_pickup": awaiting_pickup,
        "awaiting_pickup_count": len(awaiting_pickup),
        "low_stock": low_stock_parts,
        "is_receptionist_or_admin": role in ("receptionist", "admin"),
        "today": today,
    })
