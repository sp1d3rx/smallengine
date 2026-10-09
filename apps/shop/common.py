"""
Shared fixtures: db, session, auth, groups.
Everything that needs db/auth imports from here.
"""
import os
from py4web import Session, DAL, HTTP
from py4web.utils.auth import Auth
from pydal.tools.tags import Tags
from pydal.validators import *  # noqa: F401,F403

from .settings import (
    APP_FOLDER,
    DB_URI,
    DB_POOL_SIZE,
    DB_MIGRATE,
    DB_FAKE_MIGRATE,
    SESSION_SECRET_KEY,
)

# ── Session ───────────────────────────────────────────────────────────────────
session = Session(secret=SESSION_SECRET_KEY, expiration=3600)

# ── Database ──────────────────────────────────────────────────────────────────
db = DAL(
    DB_URI,
    folder=os.path.join(APP_FOLDER, "databases"),
    pool_size=DB_POOL_SIZE,
    migrate=DB_MIGRATE,
    fake_migrate=DB_FAKE_MIGRATE,
)

# ── Auth ──────────────────────────────────────────────────────────────────────
auth = Auth(session, db)

# Disable public self-registration — only admins create users via Settings
auth.param.allowed_actions = ["login", "logout", "request_reset_password", "reset_password"]

auth.enable()

# ── Groups (Tags on auth_user) ────────────────────────────────────────────────
# Provides: groups.add(user_id, "admin"), groups.get(user_id), groups.remove(...)
groups = Tags(db.auth_user, "groups")

# ── Auth helpers ──────────────────────────────────────────────────────────────

def require_user():
    """Raise HTTP 401 JSON if not logged in. Returns user dict."""
    user = auth.get_user()
    if not user:
        raise HTTP(401, '{"error":"Unauthorized"}')
    return user


def require_admin():
    """Raise HTTP 403 JSON if not in the 'admin' group. Returns user dict."""
    user = require_user()
    if "admin" not in groups.get(user["id"]):
        raise HTTP(403, '{"error":"Forbidden"}')
    return user


def require_tech():
    """Raise HTTP 403 if not a tech or admin. Returns user dict."""
    user = require_user()
    user_groups = groups.get(user["id"])
    if not {"tech", "admin"}.intersection(user_groups):
        raise HTTP(403, '{"error":"Forbidden"}')
    return user


def require_receptionist():
    """Raise HTTP 403 if not a receptionist or admin. Returns user dict."""
    user = require_user()
    user_groups = groups.get(user["id"])
    if not {"receptionist", "admin"}.intersection(user_groups):
        raise HTTP(403, '{"error":"Forbidden"}')
    return user


def is_admin(user_id) -> bool:
    """Return True if the given auth_user.id is in the admin group."""
    return "admin" in groups.get(user_id)


def get_user_role(user_id) -> str:
    """Return the highest-privilege role for a user: admin > tech > receptionist > None."""
    user_groups = set(groups.get(user_id))
    if "admin" in user_groups:
        return "admin"
    if "tech" in user_groups:
        return "tech"
    if "receptionist" in user_groups:
        return "receptionist"
    return "none"


# ── Import table definitions (side-effects: calls db.define_table) ────────────
from .data import tables  # noqa: E402,F401
