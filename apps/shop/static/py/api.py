"""Gantrika API layer — declarative Resource collections and backward-compatible wrappers."""
from gantrika.resource import Resource, ApiError, request

BASE = "/shop/api"

# ── Raw HTTP helpers ───────────────────────────────────────────────────────────
def get(url, params=None):
    return request("GET", url, params=params)

def post(url, data=None):
    return request("POST", url, data=data)

def put(url, data=None):
    return request("PUT", url, data=data)

def delete(url, params=None):
    return request("DELETE", url, params=params)


# ── Gantrika Resource Collections ──────────────────────────────────────────────
Customers = Resource(f"{BASE}/customers")
WorkOrders = Resource(f"{BASE}/workorders")
Parts = Resource(f"{BASE}/parts")
Employees = Resource(f"{BASE}/employees")
Suppliers = Resource(f"{BASE}/suppliers")
PurchaseOrders = Resource(f"{BASE}/purchaseorders")
Warranty = Resource(f"{BASE}/warranty")
Retail = Resource(f"{BASE}/retail")
Settings = Resource(f"{BASE}/settings")
Users = Resource(f"{BASE}/users")


# ── Customers & Equipment ──────────────────────────────────────────────────────
def list_customers(q=None):
    return Customers.list(q=q if q else None)

def get_customer(customer_id):
    return Customers.get(customer_id)

def create_customer(data):
    return Customers.create(data)

def update_customer(customer_id, data):
    return Customers.update(customer_id, data)

def create_equipment(customer_id, data):
    return Customers.action(customer_id, "equipment", data=data, method="POST")

def update_equipment(customer_id, equipment_id, data):
    return Customers.action(customer_id, f"equipment/{equipment_id}", data=data, method="PUT")

def delete_equipment(customer_id, equipment_id):
    return Customers.action(customer_id, f"equipment/{equipment_id}", method="DELETE")


# ── Work Orders ───────────────────────────────────────────────────────────────
def list_work_orders(status=None, employee_id=None):
    return WorkOrders.list(status=status, employee_id=employee_id)

def get_work_order(work_order_id):
    return WorkOrders.get(work_order_id)

def create_work_order(data):
    return WorkOrders.create(data)

def get_promise_date(work_type="repair"):
    return get(f"{BASE}/promise-date", {"work_type": work_type})

def advance_work_order(work_order_id, action, **kwargs):
    return WorkOrders.action(work_order_id, "status", data={"action": action, **kwargs})

def add_labor(work_order_id, data):
    return WorkOrders.action(work_order_id, "labor", data=data, method="POST")

def update_labor(work_order_id, line_id, data):
    return WorkOrders.action(work_order_id, f"labor/{line_id}", data=data, method="PUT")

def delete_labor(work_order_id, line_id):
    return WorkOrders.action(work_order_id, f"labor/{line_id}", method="DELETE")

def add_part(work_order_id, data):
    return WorkOrders.action(work_order_id, "parts", data=data, method="POST")

def delete_part(work_order_id, line_id):
    return WorkOrders.action(work_order_id, f"parts/{line_id}", method="DELETE")

def get_invoice(work_order_id):
    return WorkOrders.action(work_order_id, "invoice", method="GET")

def list_communications(work_order_id):
    return WorkOrders.action(work_order_id, "communications", method="GET")

def add_communication(work_order_id, data):
    return WorkOrders.action(work_order_id, "communications", data=data, method="POST")


# ── Parts ─────────────────────────────────────────────────────────────────────
def list_parts(q=None, low_stock=False):
    params = {}
    if q:
        params["q"] = q
    if low_stock:
        params["low_stock"] = "1"
    return Parts.list(**params)

def get_part(part_id):
    return Parts.get(part_id)

def create_part(data):
    return Parts.create(data)

def update_part(part_id, data):
    return Parts.update(part_id, data)

def adjust_part_stock(part_id, delta, reason):
    return Parts.action(part_id, "adjust", data={"delta": delta, "reason": reason})


# ── Employees ─────────────────────────────────────────────────────────────────
def list_employees(active_only=True):
    return Employees.list(active="1" if active_only else "0")

def get_employee(employee_id):
    return Employees.get(employee_id)

def create_employee(data):
    return Employees.create(data)

def update_employee(employee_id, data):
    return Employees.update(employee_id, data)

def toggle_availability(employee_id, available):
    return Employees.action(employee_id, "availability", data={"available_today": available})


# ── Warranty ──────────────────────────────────────────────────────────────────
def list_warranty_claims(status=None):
    return Warranty.list(status=status if status else None)

def create_warranty_claim(data):
    return Warranty.create(data)


# ── Sales / Inventory ─────────────────────────────────────────────────────────
def list_inventory(condition=None):
    return get(f"{BASE}/inventory", {"condition": condition} if condition else None)

def create_sale(data):
    return post(f"{BASE}/sales", data)


# ── Suppliers ─────────────────────────────────────────────────────────────────
def list_suppliers(q=None):
    return Suppliers.list(q=q if q else None)

def get_supplier(supplier_id):
    return Suppliers.get(supplier_id)

def create_supplier(data):
    return Suppliers.create(data)

def update_supplier(supplier_id, data):
    return Suppliers.update(supplier_id, data)

def create_supplier_contact(supplier_id, data):
    return Suppliers.action(supplier_id, "contacts", data=data, method="POST")

def update_supplier_contact(supplier_id, contact_id, data):
    return Suppliers.action(supplier_id, f"contacts/{contact_id}", data=data, method="PUT")

def delete_supplier_contact(supplier_id, contact_id):
    return Suppliers.action(supplier_id, f"contacts/{contact_id}", method="DELETE")


# ── Purchase Orders ───────────────────────────────────────────────────────────
def list_purchase_orders(status=None):
    return PurchaseOrders.list(status=status if status else None)

def get_purchase_order(po_id):
    return PurchaseOrders.get(po_id)

def create_purchase_order(data):
    return PurchaseOrders.create(data)

def update_purchase_order(po_id, data):
    return PurchaseOrders.update(po_id, data)

def receive_po(po_id, receipts):
    return PurchaseOrders.action(po_id, "receive", data={"receipts": receipts})

def cancel_purchase_order(po_id):
    return PurchaseOrders.action(po_id, "cancel", data={})

def add_po_line(po_id, data):
    return PurchaseOrders.action(po_id, "lines", data=data, method="POST")

def delete_po_line(po_id, line_id):
    return PurchaseOrders.action(po_id, f"lines/{line_id}", method="DELETE")


# ── Settings & Users ──────────────────────────────────────────────────────────
def get_settings():
    return Settings.list()

def update_settings(data):
    return put(f"{BASE}/settings", data)

def list_users():
    return Users.list()

def create_user(data):
    return Users.create(data)

def update_user(user_id, data):
    return Users.update(user_id, data)

def delete_user(user_id):
    return Users.delete(user_id)


# ── Retail POS ────────────────────────────────────────────────────────────────
def create_retail_sale():
    return Retail.create({})

def get_retail_sale(sale_id):
    return Retail.get(sale_id)

def search_retail_parts(q):
    return Retail.action(None, "parts", method="GET", q=q)

def add_retail_line(sale_id, part_id, quantity=1):
    return Retail.action(sale_id, "lines", data={"part_id": part_id, "quantity": quantity})

def remove_retail_line(sale_id, line_id):
    return Retail.action(sale_id, f"lines/{line_id}", method="DELETE")

def pay_retail_sale(sale_id, data):
    return Retail.action(sale_id, "pay", data=data)

def void_retail_sale(sale_id):
    return Retail.action(sale_id, "void", data={})

def return_retail_sale(sale_id, items):
    return Retail.action(sale_id, "return", data={"items": items})
