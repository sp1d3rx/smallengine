import os

APP_FOLDER = os.path.dirname(__file__)
APP_NAME = os.path.basename(APP_FOLDER)

# ── Database ──────────────────────────────────────────────────────────────────
# SQLite for now; swap to postgres later:
#   DB_URI = "postgres://user:pass@host/dbname"
DB_URI = "sqlite://storage.db"
DB_POOL_SIZE = 1
DB_MIGRATE = True
DB_FAKE_MIGRATE = False

# ── Session ───────────────────────────────────────────────────────────────────
SESSION_SECRET_KEY = "change-me-before-production"

# ── Shop configuration ────────────────────────────────────────────────────────
SHOP_NAME = "Small Engine Repair"
SHOP_ADDRESS = ""
SHOP_PHONE = ""
SHOP_EMAIL = ""

# Texas combined sales tax rate (parts & equipment only, not labor)
SALES_TAX_RATE = 0.0825

# Default hourly labor rate
DEFAULT_LABOR_RATE = 85.00

# Require customer approval for estimates above this amount
ESTIMATE_APPROVAL_THRESHOLD = 100.00
