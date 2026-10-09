"""Receptionist queue — customer communication and logistics view."""
import app
import api
from constants import WO_STATUS_LABELS as STATUS_LABELS

CONTACT_LABELS = {"call": "Call", "sms": "SMS", "email": "Email"}


def render_page():
    try:
        wo_data = api.list_work_orders(status="diagnosed,awaiting_approval,ready,closed")
    except api.ApiError as err:
        app.toast(f"Error loading queue: {err.message}", "error")
        return

    from datetime import date
    today_date = date.today()
    today = str(today_date)
    work_orders = wo_data.get("work_orders", [])

    ready_unnotified = []
    ready_notified = []
    ready_today = []
    awaiting_not_contacted = []
    awaiting_pickup = []

    for wo in work_orders:
        status = wo.get("status", "")
        if status == "ready":
            notified = wo.get("customer_notified_at")
            pickup = wo.get("date_expected_pickup")
            if pickup == today:
                ready_today.append(wo)
            elif notified:
                ready_notified.append(wo)
            else:
                ready_unnotified.append(wo)
        elif status in ("awaiting_approval", "diagnosed"):
            awaiting_not_contacted.append(wo)
        elif status == "closed" and not wo.get("date_out"):
            awaiting_pickup.append(wo)

    def _build_items(wo_list, include_days_waiting=False):
        items = []
        for wo in wo_list:
            cust = wo.get("customer") or {}
            contact_pref = CONTACT_LABELS.get(cust.get("contact_preference", "call"), "")
            phone = cust.get("phone") or ""
            email = cust.get("email") or ""
            contact_val = phone or email or "—"
            equip = wo.get("equipment") or {}
            status = wo.get("status", "")
            pickup_label = wo.get("date_expected_pickup") or "—"
            if include_days_waiting:
                ref_str = str(wo.get("modified_on") or wo.get("date_in") or "")[:10]
                try:
                    days = (today_date - date.fromisoformat(ref_str)).days if ref_str else 0
                except Exception:
                    days = 0
                pickup_label = f"{days}d waiting" + (" ⚠" if days >= 30 else "")
            items.append({
                "id": wo["id"],
                "customer_name": f"{cust.get('first_name','')} {cust.get('last_name','')}",
                "contact_info": f"{contact_pref}: {contact_val}",
                "equip_desc": f"{equip.get('make','')} {equip.get('model','')}".strip() or "—",
                "status": status,
                "status_label": STATUS_LABELS.get(status, status),
                "promised": wo.get("date_promised") or "—",
                "pickup": pickup_label,
            })
        return items

    section_defs = [
        ("Ready — not yet notified", ready_unnotified, "danger", False),
        ("Awaiting approval — needs contact", awaiting_not_contacted, "warning", False),
        ("Ready — pickup expected today", ready_today if not awaiting_not_contacted else [], "success", False),
        ("Ready — notified, no pickup date", ready_notified, "neutral", False),
        ("Closed — awaiting pickup", awaiting_pickup, "warning", True),
    ]

    sections = []
    for title, wo_list, cls, inc_days in section_defs:
        if wo_list:
            sections.append({
                "title": title,
                "cls": cls,
                "count": len(wo_list),
                "items": _build_items(wo_list, include_days_waiting=inc_days),
            })

    app.render("tpl-reception", {
        "today": today,
        "sections": sections,
    })
