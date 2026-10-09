"""
Data layer — pydal table definitions only.
No business logic here; that belongs in roles and contexts.
"""
from py4web import Field
from pydal.validators import (
    IS_NOT_EMPTY, IS_EMAIL, IS_EMPTY_OR, IS_IN_SET,
    IS_DECIMAL_IN_RANGE, IS_INT_IN_RANGE,
)
from ..common import db, auth
from ..constants import EQUIPMENT_CATEGORIES, SUPPLIER_TERMS, SHIPPING_METHODS, DEFAULT_INTAKE_DISCLAIMER

# ── Lookup sets ───────────────────────────────────────────────────────────────
CUSTOMER_TYPES = ["residential", "commercial"]
CONTACT_PREFERENCES = ["call", "sms", "email"]
WORK_TYPES = ["repair", "maintenance"]
WORK_ORDER_STATUSES = [
    "intake", "diagnosed", "awaiting_approval", "awaiting_parts",
    "in_repair", "ready", "closed", "cancelled",
]
CANCEL_REASONS = [
    "customer_declined", "customer_unresponsive",
    "not_worth_repairing", "picked_up_as_is", "other",
]
WARRANTY_CLAIM_STATUSES = ["submitted", "approved", "paid", "denied"]
INVOICE_STATUSES = ["draft", "sent", "partial", "paid", "void"]
PAYMENT_METHODS = ["cash", "card", "check", "warranty"]
EMPLOYEE_ROLES = ["owner", "tech", "receptionist"]
EQUIPMENT_CONDITIONS = ["customer_owned", "new_inventory", "renewed_inventory", "scrap"]
COMM_METHODS = ["call", "sms", "email", "in_person"]
COMM_DIRECTIONS = ["outbound", "inbound"]
PO_STATUSES = ["draft", "sent", "partial", "received", "cancelled"]

# ── Customers ─────────────────────────────────────────────────────────────────
db.define_table(
    "customer",
    Field("first_name", requires=IS_NOT_EMPTY()),
    Field("last_name", requires=IS_NOT_EMPTY()),
    Field("phone"),
    Field("email", requires=IS_EMPTY_OR(IS_EMAIL())),
    Field("contact_preference", default="call", requires=IS_IN_SET(CONTACT_PREFERENCES)),
    Field("address"),
    Field("city"),
    Field("state", default="TX"),
    Field("zip_code"),
    Field("customer_type", default="residential", requires=IS_IN_SET(CUSTOMER_TYPES)),
    Field("notes", "text"),
    auth.signature,
    format="%(first_name)s %(last_name)s",
)

# ── Suppliers (wholesale houses / distributors) ───────────────────────────────
db.define_table(
    "supplier",
    Field("name", requires=IS_NOT_EMPTY()),
    Field("phone"),
    Field("email", requires=IS_EMPTY_OR(IS_EMAIL())),
    Field("website"),
    Field("account_number"),                             # our acct # with them
    Field("terms", default="NET30", requires=IS_IN_SET(SUPPLIER_TERMS)),
    Field("default_shipping", default="ups_ground", requires=IS_IN_SET(SHIPPING_METHODS)),
    Field("notes", "text"),
    Field("active", "boolean", default=True),
    auth.signature,
    format="%(name)s",
)

db.define_table(
    "supplier_contact",
    Field("supplier_id", "reference supplier", requires=IS_NOT_EMPTY()),
    Field("name", requires=IS_NOT_EMPTY()),
    Field("title"),                                      # "Inside Sales", "Parts Dept"
    Field("phone"),
    Field("email", requires=IS_EMPTY_OR(IS_EMAIL())),
    Field("is_primary", "boolean", default=False),
    Field("notes"),
    auth.signature,
    format="%(name)s",
)

# ── Manufacturers (warranty partners) ─────────────────────────────────────────
db.define_table(
    "manufacturer",
    Field("name", requires=IS_NOT_EMPTY()),
    Field("contact_name"),
    Field("phone"),
    Field("email"),
    Field("dealer_id"),          # our dealer/account number with them
    Field("warranty_notes", "text"),
    Field("flat_rate_labor", "boolean", default=False),
    auth.signature,
    format="%(name)s",
)

# ── Employees / Technicians ───────────────────────────────────────────────────
db.define_table(
    "employee",
    Field("auth_user_id", "reference auth_user"),   # linked login account (optional)
    Field("first_name", requires=IS_NOT_EMPTY()),
    Field("last_name", requires=IS_NOT_EMPTY()),
    Field("role", default="tech", requires=IS_IN_SET(EMPLOYEE_ROLES)),
    Field("hourly_rate", "decimal(8,2)", default=0.00),
    Field("work_days", default="MTWRF"),             # e.g. "MTWRF" = Mon-Fri
    Field("available_today", "boolean", default=False),
    Field("active", "boolean", default=True),
    auth.signature,
    format="%(first_name)s %(last_name)s",
)

# ── Customer Contact Log (General CRM Interactions) ───────────────────────────
db.define_table(
    "customer_contact_log",
    Field("customer_id", "reference customer", requires=IS_NOT_EMPTY()),
    Field("employee_id", "reference employee"),
    Field("contact_date", "date", requires=IS_NOT_EMPTY()),
    Field("contact_type", default="call", requires=IS_IN_SET(["call", "email", "sms", "in_person"])),
    Field("notes", "text", requires=IS_NOT_EMPTY()),
    auth.signature,
)

# ── Equipment ─────────────────────────────────────────────────────────────────
db.define_table(
    "equipment",
    Field("customer_id", "reference customer"),      # null = shop-owned stock
    Field("category", requires=IS_IN_SET(EQUIPMENT_CATEGORIES)),
    Field("make"),
    Field("model"),
    Field("serial_number"),
    Field("year", "integer"),
    Field("condition", default="customer_owned", requires=IS_IN_SET(EQUIPMENT_CONDITIONS)),
    Field("acquisition_cost", "decimal(10,2)", default=0.00),
    Field("notes", "text"),
    auth.signature,
    format="%(make)s %(model)s (%(serial_number)s)",
)

# ── Parts Inventory ───────────────────────────────────────────────────────────
db.define_table(
    "part",
    Field("part_number", requires=IS_NOT_EMPTY()),
    Field("description", requires=IS_NOT_EMPTY()),
    Field("manufacturer_id", "reference manufacturer"),
    Field("compatible_categories", default="", notnull=True),  # comma-separated equipment categories
    Field("supplier_id", "reference supplier"),          # preferred supplier
    Field("qty_on_hand", "integer", default=0, notnull=True),
    Field("reorder_point", "integer", default=0, notnull=True),
    Field("reorder_qty", "integer", default=0, notnull=True),
    Field("cost", "decimal(10,2)", default=0.00, notnull=True),
    Field("price", "decimal(10,2)", default=0.00, notnull=True),
    Field("active", "boolean", default=True),
    auth.signature,
    format="%(part_number)s — %(description)s",
)

# ── Work Orders ───────────────────────────────────────────────────────────────
db.define_table(
    "work_order",
    Field("customer_id", "reference customer", requires=IS_NOT_EMPTY()),
    Field("equipment_id", "reference equipment", requires=IS_NOT_EMPTY()),
    Field("employee_id", "reference employee"),          # assigned tech
    Field("work_type", default="repair", requires=IS_IN_SET(WORK_TYPES)),
    Field("reported_problem", "text", requires=IS_NOT_EMPTY()),
    Field("diagnosis", "text"),
    Field("status", default="intake", requires=IS_IN_SET(WORK_ORDER_STATUSES)),
    Field("is_warranty", "boolean", default=False),
    Field("manufacturer_id", "reference manufacturer"),
    Field("cancel_reason", requires=IS_EMPTY_OR(IS_IN_SET(CANCEL_REASONS))),
    Field("cancel_reason_detail", "text"),
    Field("estimated_cost", "decimal(10,2)"),
    Field("pre_approved_limit", "decimal(10,2)"),
    Field("customer_approved", "boolean", default=False),
    Field("approval_date", "datetime"),
    Field("customer_notified_at", "datetime"),           # when customer told unit is ready
    Field("date_in", "date"),
    Field("date_promised", "date"),
    Field("date_expected_pickup", "date"),               # customer said they'll come this day
    Field("date_out", "date"),
    Field("notes", "text"),
    auth.signature,
)

# ── Work Order — Labor lines ───────────────────────────────────────────────────
db.define_table(
    "work_order_labor",
    Field("work_order_id", "reference work_order", requires=IS_NOT_EMPTY()),
    Field("employee_id", "reference employee"),
    Field("description", requires=IS_NOT_EMPTY()),
    Field("hours", "decimal(6,2)", default=0.00),
    Field("rate", "decimal(8,2)", default=0.00),
    Field("total", "decimal(10,2)", default=0.00),
    Field("is_warranty", "boolean", default=False),
    auth.signature,
)

# ── Work Order — Part lines ────────────────────────────────────────────────────
db.define_table(
    "work_order_part",
    Field("work_order_id", "reference work_order", requires=IS_NOT_EMPTY()),
    Field("part_id", "reference part"),
    Field("description"),                               # allow ad-hoc parts w/o part record
    Field("quantity", "integer", default=1),
    Field("unit_cost", "decimal(10,2)", default=0.00),
    Field("unit_price", "decimal(10,2)", default=0.00),
    Field("total", "decimal(10,2)", default=0.00),
    Field("is_warranty", "boolean", default=False),
    auth.signature,
)

# ── Work Order — Communication log ────────────────────────────────────────────
db.define_table(
    "work_order_communication",
    Field("work_order_id", "reference work_order", requires=IS_NOT_EMPTY()),
    Field("employee_id", "reference employee"),
    Field("logged_at", "datetime"),
    Field("method", requires=IS_IN_SET(COMM_METHODS)),
    Field("direction", requires=IS_IN_SET(COMM_DIRECTIONS)),
    Field("summary", "text", requires=IS_NOT_EMPTY()),
    auth.signature,
)

# ── Warranty Claims ───────────────────────────────────────────────────────────
db.define_table(
    "warranty_claim",
    Field("work_order_id", "reference work_order", requires=IS_NOT_EMPTY()),
    Field("manufacturer_id", "reference manufacturer", requires=IS_NOT_EMPTY()),
    Field("mfr_claim_number"),
    Field("submitted_date", "date"),
    Field("covered_labor", "decimal(10,2)", default=0.00),
    Field("covered_parts", "decimal(10,2)", default=0.00),
    Field("status", default="submitted", requires=IS_IN_SET(WARRANTY_CLAIM_STATUSES)),
    Field("reimbursement_amount", "decimal(10,2)"),
    Field("payment_date", "date"),
    Field("notes", "text"),
    auth.signature,
)

# ── Equipment Sales + Retail ───────────────────────────────────────────────────
RETAIL_SALE_STATUSES = ["open", "paid", "voided"]

db.define_table(
    "sale",
    # Linkage — both nullable; work_order_id ties retail sale to a shop visit
    Field("work_order_id", "reference work_order"),
    Field("customer_id", "reference customer"),          # null = walk-in
    Field("cash_customer_name"),                         # free-text for walk-ins
    Field("employee_id", "reference employee"),
    # Equipment-sale fields (kept for backward compat with SellEquipmentContext)
    Field("equipment_id", "reference equipment"),
    Field("sale_price", "decimal(10,2)", default=0.00),
    Field("trade_in_equipment_id", "reference equipment"),
    Field("trade_in_value", "decimal(10,2)", default=0.00),
    # Totals (retail line-item driven; equipment sales compute their own total)
    Field("subtotal", "decimal(10,2)", default=0.00),
    Field("tax_rate", "decimal(6,4)", default=0.0825),
    Field("tax_amount", "decimal(10,2)", default=0.00),
    Field("total", "decimal(10,2)", default=0.00),
    Field("payment_method", requires=IS_EMPTY_OR(IS_IN_SET(PAYMENT_METHODS))),
    Field("payment_reference"),
    Field("status", default="open", requires=IS_IN_SET(RETAIL_SALE_STATUSES)),
    Field("notes", "text"),
    Field("sale_date", "date"),
    auth.signature,
)

db.define_table(
    "sale_line",
    Field("sale_id", "reference sale", requires=IS_NOT_EMPTY()),
    Field("part_id", "reference part"),
    Field("description", requires=IS_NOT_EMPTY()),
    Field("quantity", "integer", default=1),
    Field("unit_price", "decimal(10,2)", default=0.00),
    Field("unit_cost", "decimal(10,2)", default=0.00),
    Field("total", "decimal(10,2)", default=0.00),
    auth.signature,
)

# ── Invoices ──────────────────────────────────────────────────────────────────
db.define_table(
    "invoice",
    Field("work_order_id", "reference work_order"),
    Field("sale_id", "reference sale"),
    Field("customer_id", "reference customer", requires=IS_NOT_EMPTY()),
    Field("subtotal", "decimal(10,2)", default=0.00),
    Field("tax_amount", "decimal(10,2)", default=0.00),
    Field("total", "decimal(10,2)", default=0.00),
    Field("status", default="draft", requires=IS_IN_SET(INVOICE_STATUSES)),
    Field("due_date", "date"),
    Field("notes", "text"),
    auth.signature,
)

# ── Payments ──────────────────────────────────────────────────────────────────
db.define_table(
    "payment",
    Field("invoice_id", "reference invoice", requires=IS_NOT_EMPTY()),
    Field("amount", "decimal(10,2)", requires=IS_DECIMAL_IN_RANGE(0.01)),
    Field("method", requires=IS_IN_SET(PAYMENT_METHODS)),
    Field("reference"),
    Field("received_on", "date"),
    Field("notes", "text"),
    auth.signature,
)

# ── Shop settings (single-row config) ────────────────────────────────────────
db.define_table(
    "shop_settings",
    Field("shop_name", default="Certified Small Engine"),
    Field("address"),
    Field("city"),
    Field("state", default="TX"),
    Field("zip_code"),
    Field("phone"),
    Field("email"),
    Field("tax_rate", "decimal(6,4)", default=0.0825),
    Field("default_labor_rate", "decimal(8,2)", default=85.00),
    Field("estimate_approval_threshold", "decimal(10,2)", default=100.00),
    Field("intake_disclaimer", "text", default=DEFAULT_INTAKE_DISCLAIMER),
)

# ── Purchase Orders ───────────────────────────────────────────────────────────
db.define_table(
    "purchase_order",
    Field("po_number", requires=IS_NOT_EMPTY()),         # e.g. "PO-2026-001"
    Field("supplier_id", "reference supplier", requires=IS_NOT_EMPTY()),
    Field("status", default="draft", requires=IS_IN_SET(PO_STATUSES)),
    Field("ordered_on", "date"),
    Field("expected_by", "date"),
    Field("shipping_method", requires=IS_EMPTY_OR(IS_IN_SET(SHIPPING_METHODS))),
    Field("tracking_number"),
    Field("notes", "text"),
    Field("total", "decimal(10,2)", default=0.00),
    auth.signature,
    format="%(po_number)s",
)

db.define_table(
    "purchase_order_line",
    Field("po_id", "reference purchase_order", requires=IS_NOT_EMPTY()),
    Field("part_id", "reference part"),                  # nullable: non-catalog items
    Field("description", requires=IS_NOT_EMPTY()),
    Field("qty_ordered", "integer", default=1, requires=IS_INT_IN_RANGE(1, None)),
    Field("unit_cost", "decimal(10,2)", default=0.00),
    Field("total_cost", "decimal(10,2)", default=0.00),  # qty_ordered * unit_cost
    Field("qty_received", "integer", default=0),
    auth.signature,
)

# ── Parts stock adjustments (audit trail) ─────────────────────────────────────
db.define_table(
    "stock_adjustment",
    Field("part_id", "reference part", requires=IS_NOT_EMPTY()),
    Field("delta", "integer"),
    Field("reason"),
    Field("reference_id", "integer"),
    Field("notes"),
    auth.signature,
)
