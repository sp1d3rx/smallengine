# Small Engine Repair Shop — LOB App Outline

## Business Context

Texas-based small engine repair shop providing:
- **Repair services**: mowers, leaf blowers, chainsaws, trimmers, generators, etc.
- **Warranty repair**: authorized warranty work on behalf of manufacturers
- **Sales**: new and renewed/refurbished equipment

**Stack**: py4web (JSON API + static files) | Mustache (client-side templates) | Brython (no JS)

---

## Core Modules

### 1. Customers
- Name, phone, email, address
- Preferred contact method
- Customer type: residential / commercial
- Full history: repairs, purchases, warranty claims

### 2. Equipment Registry
Each piece of equipment brought in or sold is tracked:
- Category (mower, chainsaw, blower, trimmer, generator, other)
- Make, model, serial number, year
- Ownership: linked to customer (or "shop stock" if unsold)
- Condition flag: customer-owned | new inventory | renewed inventory
- Equipment history: all work orders and repairs

### 3. Work Orders (Repair Tickets)
Core workflow of the shop:
- Intake: customer + equipment + reported problem
- Diagnosis: tech notes, identified parts needed
- Status: `intake → diagnosed → awaiting_parts → in_repair → ready → closed`
- Labor line items (tech, hours, rate)
- Parts line items (from parts inventory)
- Warranty flag: is this a warranty repair?
- Estimated completion date
- Customer approval for estimates (email/SMS gate before proceeding)
- Photos (stored as static files, linked to work order)

### 4. Warranty Claims
Tracks manufacturer warranty work separately from regular repairs:
- Manufacturer (linked to Manufacturer table)
- Manufacturer claim/RO number
- Work order linked
- Covered parts and labor amounts
- Reimbursement status: `submitted → approved → paid → denied`
- Submission date, payment received date
- Notes/documentation requirements per manufacturer

### 5. Parts Inventory
- Part number, description, manufacturer, supplier
- Quantity on hand, reorder point, reorder quantity
- Cost price, sell price
- Parts consumed by work orders (decrements stock)
- Purchase orders to restock (basic PO tracking)

### 6. Sales (Equipment Sales)
- Sell new or renewed equipment from shop inventory
- Linked to customer
- Sale price, discount, tax (Texas sales tax — taxable vs. exempt)
- Trade-in equipment (assigned to renewed inventory or scrap)
- Sales receipt generation

### 7. Invoices & Payments
- Generated from closed work orders or sales
- Line items: labor + parts + fees
- Texas sales tax applied to parts (labor typically non-taxable)
- Payment methods: cash, card, check, warranty reimbursement
- Partial payments / balance tracking
- Invoice status: `draft → sent → partial → paid → void`

### 8. Manufacturers
- Manufacturer name, contact, rep name
- Warranty authorization codes / dealer ID
- Covered equipment categories
- Warranty claim submission process notes (per-manufacturer)
- Reimbursement rates (flat rate labor per job code, if applicable)

### 9. Employees / Technicians
- Name, role (tech, service writer, owner)
- Labor rate (for cost tracking)
- Work orders assigned

---

## Data Model (py4web / pydal)

```
customer(id, first_name, last_name, phone, email, address, city, zip,
         customer_type, notes, created_on)

equipment(id, customer_id, category, make, model, serial_number, year,
          condition, purchase_date, notes)

manufacturer(id, name, contact_name, phone, email, dealer_id,
             warranty_notes, labor_rate_type)

employee(id, first_name, last_name, role, hourly_rate, active)

work_order(id, customer_id, equipment_id, employee_id,
           reported_problem, diagnosis, status,
           is_warranty, manufacturer_id,
           estimated_cost, approved_by_customer, approval_date,
           date_in, date_promised, date_out,
           notes, created_on)

work_order_labor(id, work_order_id, employee_id, description,
                 hours, rate, total)

work_order_part(id, work_order_id, part_id, quantity, unit_cost,
                unit_price, total)

part(id, part_number, description, manufacturer_id, supplier,
     qty_on_hand, reorder_point, reorder_qty, cost, price, active)

warranty_claim(id, work_order_id, manufacturer_id,
               mfr_claim_number, submitted_date,
               covered_labor, covered_parts,
               status, reimbursement_amount, payment_date, notes)

sale(id, customer_id, equipment_id, employee_id,
     sale_price, trade_in_value, trade_in_equipment_id,
     tax_rate, tax_amount, total, payment_method, notes, sale_date)

invoice(id, work_order_id, sale_id, customer_id,
        subtotal, tax_amount, total,
        status, due_date, notes, created_on)

payment(id, invoice_id, amount, method, reference, received_on, notes)
```

---

## Pages / Views

### Dashboard (`/`)
- Open work orders by status (kanban-style count cards)
- Work orders overdue or past promised date
- Today's ready-for-pickup
- Low stock parts alerts
- Pending warranty reimbursements

### Customers (`/customers`)
- List with search (name, phone)
- Customer detail: info + full history (work orders, sales, equipment)
- Create / Edit form

### Equipment (`/equipment`)
- List by customer or all shop equipment
- Equipment detail: history of all work done
- Create / Edit

### Work Orders (`/workorders`)
- List with filters: status, tech, date range, warranty-only
- Work order detail: full view — labor, parts, status, photos
- Create (intake form): customer lookup or quick-create, equipment lookup or add
- Edit / progress through status pipeline
- Print-friendly view for customer receipt / work authorization

### Warranty Claims (`/warranty`)
- List: open claims, by manufacturer, by status
- Claim detail: linked work order, docs, reimbursement tracking
- Create / Edit
- Summary: total submitted vs. paid per manufacturer (monthly)

### Parts Inventory (`/parts`)
- List with search, filter by low stock
- Part detail
- Create / Edit
- Restock / adjust quantity
- Basic purchase order list

### Sales (`/sales`)
- List of equipment sales
- Sale detail / receipt
- New sale form: pick inventory item, customer, handle trade-in

### Invoices (`/invoices`)
- List: unpaid, by customer
- Invoice detail with line items
- Record payment
- Printable invoice

### Reports (`/reports`)
- Revenue by period (labor vs. parts vs. sales)
- Work orders completed per tech
- Warranty reimbursements (submitted vs. received)
- Inventory value
- Customer equipment history export

### Settings (`/settings`)
- Shop info (name, address, phone — used on invoices)
- Tax rate
- Labor rates defaults
- Manage employees
- Manage manufacturers

---

## py4web API Endpoints (JSON)

```
GET/POST   /api/customers
GET/PUT    /api/customers/<id>

GET/POST   /api/equipment
GET/PUT    /api/equipment/<id>

GET/POST   /api/workorders
GET/PUT    /api/workorders/<id>
POST       /api/workorders/<id>/status       # advance status
POST       /api/workorders/<id>/labor        # add labor line
POST       /api/workorders/<id>/parts        # add part line
DELETE     /api/workorders/<id>/labor/<lid>
DELETE     /api/workorders/<id>/parts/<pid>

GET/POST   /api/warranty
GET/PUT    /api/warranty/<id>

GET/POST   /api/parts
GET/PUT    /api/parts/<id>
POST       /api/parts/<id>/adjust            # stock adjustment

GET/POST   /api/sales
GET        /api/sales/<id>

GET        /api/invoices
GET        /api/invoices/<id>
POST       /api/invoices/<id>/payment

GET        /api/reports/<report_name>

GET/POST   /api/manufacturers
GET/PUT    /api/manufacturers/<id>

GET/POST   /api/employees
GET/PUT    /api/employees/<id>
```

---

## Client-Side Architecture (Brython + Mustache)

```
static/
  templates/
    base.html              # shell: nav, flash messages
    dashboard.html
    customers/
      list.mustache
      detail.mustache
      form.mustache
    workorders/
      list.mustache
      detail.mustache
      form.mustache
      status_badge.mustache
    warranty/
      list.mustache
      detail.mustache
    parts/
      list.mustache
      form.mustache
    sales/
      list.mustache
      detail.mustache
    invoices/
      detail.mustache
    reports/
      revenue.mustache
  py/
    app.py                 # Brython: router, fetch helpers, global state
    api.py                 # Brython: thin wrappers for each API endpoint
    components.py          # Brython: shared UI behaviors (modals, toasts, etc.)
    pages/
      dashboard.py
      customers.py
      workorders.py
      warranty.py
      parts.py
      sales.py
      invoices.py
      reports.py
  css/
    app.css                # minimal custom styles (use a classless CSS framework)
```

**Brython pattern per page:**
1. Page script calls `api.fetch(endpoint)` on load
2. Response JSON is passed to `Mustache.render(template, data)`
3. Rendered HTML is injected into `#content` div
4. Form submissions serialize to dict → `api.post(endpoint, data)` → re-render

---

## Key Business Rules

- **Texas sales tax**: applied to parts/equipment sold, not labor. ~8.25% (varies by city). Configurable per shop location.
- **Warranty work**: customer is not invoiced for covered portions; shop invoices manufacturer instead.
- **Customer approval gate**: estimates over a configurable threshold require documented customer approval before work begins.
- **Renewed equipment**: shop-refurbished equipment has its own cost-of-goods tracked (original acquisition + labor + parts to refurb).
- **Trade-ins**: accepted equipment enters inventory as renewed stock or scrap, with acquisition value recorded for margin tracking.

---

## Suggested Build Order

1. **Foundation**: py4web project setup, DB schema, auth (single-user or simple role)
2. **Customers + Equipment**: CRUD, the lookup used everywhere else
3. **Work Orders**: intake → close flow, the core of the app
4. **Parts Inventory**: needed for work order line items
5. **Invoices + Payments**: close the cash loop
6. **Warranty Claims**: layer on top of work orders
7. **Sales**: sell inventory items
8. **Reports + Dashboard**: visibility into all of the above
9. **Print views**: work authorization forms, invoices, receipts
