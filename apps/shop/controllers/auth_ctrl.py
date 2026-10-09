"""
Auth-adjacent controllers:
  - /setup      first-run admin account creation
  - /api/me     current user + groups (for Brython)
  - /api/users  user management (admin only)
"""
from py4web import action, request, redirect, URL, HTTP
from pydal.validators import CRYPT, IS_EMAIL
from ..common import db, auth, session, groups, require_user, require_admin, is_admin


# ── First-run setup ───────────────────────────────────────────────────────────

@action("setup", method=["GET"])
@action.uses("setup.html", db, session)
def setup_get():
    if db(db.auth_user).count() > 0:
        redirect(URL("index"))
    return dict(errors={})


@action("setup", method=["POST"])
@action.uses("setup.html", db, session)
def setup_post():
    if db(db.auth_user).count() > 0:
        redirect(URL("index"))

    first_name = (request.forms.get("first_name") or "").strip()
    last_name  = (request.forms.get("last_name")  or "").strip()
    email      = (request.forms.get("email")      or "").strip().lower()
    password   = (request.forms.get("password")   or "")
    confirm    = (request.forms.get("confirm")    or "")

    errors = {}
    if not first_name:
        errors["first_name"] = "Required"
    if not last_name:
        errors["last_name"] = "Required"
    if not email or not IS_EMAIL()(email)[1] is None:
        # IS_EMAIL returns (value, error); error is None when valid
        val, err = IS_EMAIL()(email)
        if err:
            errors["email"] = "Valid email required"
    if len(password) < 8:
        errors["password"] = "At least 8 characters"
    if password != confirm:
        errors["confirm"] = "Passwords do not match"

    if errors:
        return dict(errors=errors)

    hashed = CRYPT()(password)[0]
    user_id = db.auth_user.insert(
        first_name=first_name,
        last_name=last_name,
        email=email,
        password=hashed,
    )
    groups.add(user_id, "admin")

    # Also initialise shop settings row if missing
    if db(db.shop_settings).count() == 0:
        db.shop_settings.insert()

    db.commit()
    redirect(URL("auth", "login"))


# ── Current user (called by Brython on page load) ─────────────────────────────

@action("api/me", method=["GET"])
@action.uses(db, session, auth)
def me():
    user = auth.get_user()
    if not user:
        return dict(user=None)
    user_groups = groups.get(user["id"])
    return dict(user=dict(
        id=user["id"],
        email=user.get("email", ""),
        first_name=user.get("first_name", ""),
        last_name=user.get("last_name", ""),
        groups=user_groups,
        is_admin="admin" in user_groups,
    ))


# ── User management (admin only) ──────────────────────────────────────────────

@action("api/users", method=["GET"])
@action.uses(db, session, auth)
def users_list():
    require_admin()
    rows = db(db.auth_user).select(
        db.auth_user.id, db.auth_user.first_name, db.auth_user.last_name,
        db.auth_user.email,
        orderby=db.auth_user.last_name,
    )
    result = []
    for r in rows:
        d = r.as_dict()
        d["groups"] = groups.get(r.id)
        role_set = set(d["groups"])
        d["role"] = next(
            (role for role in ("admin", "tech", "receptionist") if role in role_set),
            "none",
        )
        d["is_admin"] = "admin" in role_set
        result.append(d)
    return dict(users=result)


@action("api/users", method=["POST"])
@action.uses(db, session, auth)
def users_create():
    require_admin()
    data = request.json or {}

    email      = (data.get("email")      or "").strip().lower()
    password   = (data.get("password")   or "")
    first_name = (data.get("first_name") or "").strip()
    last_name  = (data.get("last_name")  or "").strip()
    role       = (data.get("role")       or "tech")

    valid_roles = {"admin", "tech", "receptionist"}
    if role not in valid_roles:
        role = "tech"

    errors = {}
    if not first_name:
        errors["first_name"] = "Required"
    if not last_name:
        errors["last_name"] = "Required"
    _, err = IS_EMAIL()(email)
    if err:
        errors["email"] = "Valid email required"
    elif db(db.auth_user.email == email).count():
        errors["email"] = "Email already in use"
    if len(password) < 8:
        errors["password"] = "At least 8 characters"
    if errors:
        raise HTTP(422, str(errors))

    hashed = CRYPT()(password)[0]
    user_id = db.auth_user.insert(
        first_name=first_name,
        last_name=last_name,
        email=email,
        password=hashed,
    )
    groups.add(user_id, role)

    # Auto-create linked employee record for tech/receptionist
    if role in ("tech", "receptionist"):
        db.employee.insert(
            auth_user_id=user_id,
            first_name=first_name,
            last_name=last_name,
            role=role,
        )

    db.commit()
    return dict(id=user_id)


@action("api/users/<user_id:int>", method=["GET"])
@action.uses(db, session, auth)
def users_get(user_id):
    require_admin()
    row = db.auth_user[user_id]
    if not row:
        raise HTTP(404)
    d = dict(
        id=row.id,
        first_name=row.first_name,
        last_name=row.last_name,
        email=row.email,
    )
    d["groups"] = groups.get(user_id)
    d["is_admin"] = "admin" in d["groups"]
    return dict(user=d)


@action("api/users/<user_id:int>", method=["PUT"])
@action.uses(db, session, auth)
def users_update(user_id):
    current = require_admin()
    row = db.auth_user[user_id]
    if not row:
        raise HTTP(404)
    data = request.json or {}

    update = {}
    if "first_name" in data:
        update["first_name"] = data["first_name"]
    if "last_name" in data:
        update["last_name"] = data["last_name"]
    if "email" in data:
        update["email"] = data["email"].strip().lower()
    if "password" in data and data["password"]:
        if len(data["password"]) < 8:
            raise HTTP(422, '{"error":"Password too short"}')
        update["password"] = CRYPT()(data["password"])[0]

    if update:
        db(db.auth_user.id == user_id).update(**update)

    # Role changes — prevent removing own admin status
    if "role" in data and data["role"] in {"admin", "tech", "receptionist"}:
        new_role = data["role"]
        current_groups = set(groups.get(user_id))
        for old_role in current_groups.intersection({"admin", "tech", "receptionist"}):
            if old_role == "admin" and user_id == current["id"]:
                continue   # never remove your own admin
            groups.remove(user_id, old_role)
        groups.add(user_id, new_role)

    db.commit()
    return dict(ok=True)


@action("api/users/<user_id:int>", method=["DELETE"])
@action.uses(db, session, auth)
def users_delete(user_id):
    current = require_admin()
    if user_id == current["id"]:
        raise HTTP(400, '{"error":"Cannot delete your own account"}')
    if not db.auth_user[user_id]:
        raise HTTP(404)
    db(db.auth_user.id == user_id).delete()
    db.commit()
    return dict(ok=True)


# ── Shop settings API (admin only) ────────────────────────────────────────────

@action("api/settings", method=["GET"])
@action.uses(db, session, auth)
def settings_get():
    require_admin()
    row = db(db.shop_settings).select().first()
    if not row:
        row_id = db.shop_settings.insert()
        row = db.shop_settings[row_id]
    return dict(settings=row.as_dict())


@action("api/settings", method=["PUT"])
@action.uses(db, session, auth)
def settings_update():
    require_admin()
    data = request.json or {}
    allowed = [
        "shop_name", "address", "city", "state", "zip_code",
        "phone", "email", "tax_rate", "default_labor_rate",
        "estimate_approval_threshold", "intake_disclaimer",
    ]
    update = {k: data[k] for k in allowed if k in data}
    row = db(db.shop_settings).select().first()
    if row:
        db(db.shop_settings.id == row.id).update(**update)
    else:
        db.shop_settings.insert(**update)
    db.commit()
    return dict(ok=True)
