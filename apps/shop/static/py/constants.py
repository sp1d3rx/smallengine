"""
Client-side constants — fetched from GET /shop/api/constants (synchronous).
Single source of truth: apps/shop/data/constants.yaml
Do not hardcode values here; edit the YAML file instead.
"""
import json
from browser import ajax

def _fetch():
    req = ajax.ajax()
    req.open("GET", "/shop/api/constants", False)  # False = synchronous
    req.set_header("X-Requested-With", "XMLHttpRequest")
    req.send("")
    if req.status == 200:
        try:
            return json.loads(req.text)
        except Exception:
            pass
    return {}

_raw = _fetch()


def _pairs(key):
    """Return [(value, label), ...] tuples for a given key."""
    return [(item["value"], item["label"]) for item in _raw.get(key, [])]

def _label_map(key):
    """Return {value: label} dict for a given key."""
    return {item["value"]: item["label"] for item in _raw.get(key, [])}


# Equipment categories
EQUIPMENT_CATEGORIES       = _pairs("equipment_categories")
EQUIPMENT_CATEGORY_LABELS  = _label_map("equipment_categories")

# Supplier payment terms
SUPPLIER_TERMS             = _pairs("supplier_terms")
SUPPLIER_TERMS_LABELS      = _label_map("supplier_terms")

# Shipping methods
SHIPPING_METHODS           = _pairs("shipping_methods")
SHIPPING_METHOD_LABELS     = _label_map("shipping_methods")

# Work order statuses (not in YAML — internal app states, not user-editable)
WO_STATUS_LABELS = {
    "intake":            "Intake",
    "diagnosed":         "Diagnosed",
    "awaiting_approval": "Awaiting Approval",
    "awaiting_parts":    "Awaiting Parts",
    "in_repair":         "In Repair",
    "ready":             "Ready",
    "closed":            "Closed",
    "cancelled":         "Cancelled",
}
