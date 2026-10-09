"""
Employee API endpoints — shop staff management (admin only for CRUD, any user for availability).
"""
from py4web import action, request, HTTP
from ..common import db, auth, session, require_user, require_admin


@action("api/employees", method=["GET"])
@action.uses(db, session, auth)
def employees_list():
    require_user()
    active_only = request.query.get("active", "1") == "1"
    query = db.employee.id > 0
    if active_only:
        query &= db.employee.active == True
    rows = db(query).select(orderby=db.employee.last_name | db.employee.first_name)
    return dict(employees=[r.as_dict() for r in rows])


@action("api/employees", method=["POST"])
@action.uses(db, session, auth)
def employees_create():
    require_admin()
    data = request.json or {}
    result = db.employee.validate_and_insert(**{
        k: data.get(k) for k in [
            "first_name", "last_name", "role", "hourly_rate",
            "work_days", "auth_user_id",
        ]
    })
    if result.get("errors"):
        raise HTTP(422, str(result["errors"]))
    db.commit()
    return dict(id=result["id"])


@action("api/employees/<employee_id:int>", method=["GET"])
@action.uses(db, session, auth)
def employees_get(employee_id):
    require_user()
    row = db.employee[employee_id]
    if not row:
        raise HTTP(404)
    return dict(employee=row.as_dict())


@action("api/employees/<employee_id:int>", method=["PUT"])
@action.uses(db, session, auth)
def employees_update(employee_id):
    require_admin()
    if not db.employee[employee_id]:
        raise HTTP(404)
    data = request.json or {}
    allowed = ["first_name", "last_name", "role", "hourly_rate", "work_days",
               "active", "auth_user_id"]
    db(db.employee.id == employee_id).update(**{k: data[k] for k in allowed if k in data})
    db.commit()
    return dict(ok=True)


@action("api/employees/<employee_id:int>/availability", method=["POST"])
@action.uses(db, session, auth)
def employees_toggle_availability(employee_id):
    """Any logged-in user can toggle their own availability; admin can toggle anyone's."""
    user = require_user()
    row = db.employee[employee_id]
    if not row:
        raise HTTP(404)

    # Non-admins can only toggle their own availability
    from ..common import groups
    if "admin" not in groups.get(user["id"]):
        linked = db(db.employee.auth_user_id == user["id"]).select().first()
        if not linked or linked.id != employee_id:
            raise HTTP(403, '{"error":"Forbidden"}')

    data = request.json or {}
    available = bool(data.get("available_today", not row.available_today))
    db(db.employee.id == employee_id).update(available_today=available)
    db.commit()
    return dict(available_today=available)
