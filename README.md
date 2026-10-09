# Small Engine Repair Shop

A line-of-business (LOB) web app for a small engine repair shop. It covers the full
shop workflow: customer intake, work orders, parts inventory, purchasing, warranty
claims, equipment sales, invoicing, and reporting.

Built entirely in Python — **no JavaScript**. The backend is [py4web](https://py4web.com)
serving a JSON API plus static files; the frontend is [Brython](https://brython.info)
(Python in the browser) rendering [Handlebars](https://handlebarsjs.com/) templates.

## Features

- **Customers** — profiles, contact history, and full repair/purchase history
- **Equipment registry** — make/model/serial tracking, ownership, and condition
- **Work orders** — intake → diagnosis → repair → ready → close pipeline, with
  labor and parts line items and a customer-approval gate
- **Parts inventory** — stock levels, reorder points, and stock adjustments
- **Purchasing** — suppliers and purchase orders to restock parts
- **Warranty claims** — manufacturer reimbursement tracking, separate from customer billing
- **Sales** — new and renewed equipment sales with trade-ins
- **Invoices & payments** — generated from work orders or sales, with partial payments
- **Reports** — revenue, work-order throughput, warranty reimbursements, inventory value
- **Roles** — admin, tech, and receptionist with per-role access control

## Tech stack

| Layer     | Technology |
|-----------|------------|
| Backend   | py4web (JSON API + static files) |
| ORM       | pydal |
| Frontend  | Brython (Python in the browser) |
| Templates | Handlebars (client-side) |
| Database  | SQLite (default) — swap to Postgres via `DB_URI` |

## Getting started

Requires Python 3.10+.

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app (from the project root, where apps/ lives)
python -m py4web
```

Then open http://127.0.0.1:8000/shop. On first run you'll be taken to a setup page
to create the initial admin account.

### Configuration

Shop-specific settings live in [`apps/shop/settings.py`](apps/shop/settings.py):

- `DB_URI` — database connection string (defaults to `sqlite://storage.db`)
- `SESSION_SECRET_KEY` — **change this before deploying**
- `SHOP_NAME`, `SHOP_ADDRESS`, `SHOP_PHONE`, `SHOP_EMAIL` — used on invoices
- `SALES_TAX_RATE` — Texas combined sales tax (parts/equipment only, not labor)
- `DEFAULT_LABOR_RATE` — default hourly labor rate
- `ESTIMATE_APPROVAL_THRESHOLD` — estimates above this require customer approval

Coded-list values (equipment categories, supplier terms, shipping methods) are defined
in a single source of truth at [`apps/shop/data/constants.yaml`](apps/shop/data/constants.yaml).

## Architecture

The app follows the **DCI** (Data, Context, Interaction) pattern:

- **Data** — pydal table definitions in [`apps/shop/data/tables.py`](apps/shop/data/tables.py)
- **Roles** — mixin classes in [`apps/shop/roles/`](apps/shop/roles/) that attach behavior
  to domain rows (customers, equipment, work orders, parts, sales)
- **Contexts** — use-case objects in [`apps/shop/contexts/`](apps/shop/contexts/) that hold
  business logic (repair, warranty, sales, inventory, purchasing, accounting)
- **Controllers** — a thin HTTP layer in [`apps/shop/controllers/`](apps/shop/controllers/)
  that parses the request, delegates to a context, and returns JSON

Controllers stay thin: business rules belong in contexts, and row behavior belongs in roles.

### Gantrika

**Gantrika** is the thin, home-grown framework layer that spans the whole stack. It is not a
dependency — it is vendored in this repo (see `apps/shop/gantrika/` and
`apps/shop/static/py/gantrika/`) and is the only thing standing between your DCI code and the
raw py4web/Brython plumbing.

The name is a diminutive of **gantry**, borrowed through Russian: *гантри* (*gantri*) + the
diminutive suffix *-ка* (*-ka*) → **гантрика** (*gantrika*), "little gantry." A gantry is a
load-bearing frame that spans a structure without being the structure itself — which is exactly
what this library does: a small, load-bearing frame over py4web + Brython, not a full framework.

It is split into two halves that share the name:

**Server half — [`apps/shop/gantrika/`](apps/shop/gantrika/)** (the DCI service-layer glue)

| Module | Provides |
|--------|----------|
| `response.py` | Standard JSON envelope: `json_ok`, `json_error`, `json_paginated` — every endpoint returns the same `{status, data, meta}` / `{status, error, errors}` shape |
| `context.py` | `BaseContext` (base for all `contexts/`): holds `db`/`auth`, a `transaction()` commit/rollback context manager, `validate_required()`, `filter_allowed()`; plus `ValidationError`, `NotFoundError`, `BusinessRuleError` |

**Client half — [`apps/shop/static/py/gantrika/`](apps/shop/static/py/gantrika/)** (a desktop-class Python SPA framework for Brython)

| Module | Provides |
|--------|----------|
| `router.py` | Declarative hash router: `<name:int>`/`<name:float>`/`<name:str>` param patterns compiled to regex, `before_each`/`after_each` navigation guards, 404 + error handlers, auto active-state on nav links |
| `resource.py` | Declarative REST client: `Resource(base_url)` → `.list/.get/.create/.update/.patch/.delete/.action` over a synchronous `request()` bridge on Brython `ajax`; raises `ApiError` on non-2xx |
| `store.py` | Central state store + event emitter: `get/set/update`, per-key or `*` `subscribe`, and `on/emit` for named events |
| `view.py` | `View` base class with lifecycle hooks `mount → render → bind_events → unmount` and `on_click/on_input/on_change/on_submit` helpers |
| `split_view.py` | `SplitPaneView`: master-detail two-column workbench with built-in debounced live search + row-selection state |
| `ui.py` | `Toast`, `Modal` (incl. `confirm` dialogs), Handlebars template compile/render, and the `safe_action` decorator (traps `ApiError` → error toast) |
| `forms.py` | Two-way form binding: `form_data` (DOM → dict, with type coercion), `populate_form` (dict → DOM), inline `set_form_errors`/`clear_form_errors` |
| `formatters.py` | Domain formatting vocabulary: `currency`, `short_date`, `local_time`, `human_days_ago`, `percentage`, `delta_qty` |

**Design philosophy.** One language end-to-end — the same Python on server and client, with only
Handlebars templates and CSS as non-Python. Gantrika is opinionated but tiny: it does not replace
py4web/pydal, it standardizes the JSON contract, the service layer, and the SPA ergonomics.
Server = DCI (roles/contexts/controllers); client = SPA (router/store/view/resource).

### Project structure

```
apps/shop/
  common.py            # shared fixtures: db, session, auth, groups, role guards
  constants.py         # server-side constants (loaded from data/constants.yaml)
  settings.py          # shop configuration
  data/
    tables.py          # pydal table definitions
    constants.yaml     # coded-list values (single source of truth)
  roles/               # DCI roles (mixin behavior on domain rows)
  contexts/            # DCI contexts (business logic / use cases)
  controllers/         # thin HTTP layer (JSON API + page routes)
  gantrika/            # Gantrika server half (JSON envelope, BaseContext, domain errors)
  templates/           # server-rendered shell + Handlebars partials
  static/
    py/                # Brython (client-side Python)
      gantrika/        # Gantrika client half (router, resource, store, view, ui, forms, formatters)
    css/               # app.css
    templates/         # client-side templates
  example/             # standalone design mockups
```

## Design

The full product outline — business context, data model, page inventory, and API
surface — is in [`OUTLINE.md`](OUTLINE.md).

## License

[MIT](LICENSE)
