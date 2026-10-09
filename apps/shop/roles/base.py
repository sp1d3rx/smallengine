"""
DCI Role infrastructure.

Roles are mixin classes whose methods assume `self` is a pydal Row
(or a RoleObject wrapping one).  Use `cast(row, RoleClass)` to assign
a role to a data object at runtime.
"""


class RoleObject:
    """
    Thin wrapper around a pydal Row that supports dynamic role assignment.
    Attribute access falls through to the underlying row so roles can read
    field values with plain `self.field_name`.
    """

    def __init__(self, row, table_name: str = ""):
        object.__setattr__(self, "_row", row)
        object.__setattr__(self, "_table", table_name)

    # ── Transparent field access ──────────────────────────────────────────────
    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_row"), name)

    def __setattr__(self, name, value):
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            setattr(object.__getattribute__(self, "_row"), name, value)

    def __repr__(self):
        table = object.__getattribute__(self, "_table")
        row = object.__getattribute__(self, "_row")
        return f"<RoleObject({table}) id={getattr(row, 'id', '?')}>"

    def as_dict(self):
        row = object.__getattribute__(self, "_row")
        return row.as_dict() if hasattr(row, "as_dict") else dict(row)


def cast(row, *role_classes, table_name: str = ""):
    """
    Wrap a pydal Row in a RoleObject and dynamically mix in one or more roles.

    Usage:
        wo = cast(db.work_order[id], BillableWorkRole, WarrantyEligibleRole,
                  table_name="work_order")
        wo.calculate_total()   # from BillableWorkRole
        wo.is_warranty_covered()  # from WarrantyEligibleRole
    """
    base = RoleObject(row, table_name)
    if not role_classes:
        return base
    combined = type(
        "".join(rc.__name__ for rc in role_classes),
        (*role_classes, RoleObject),
        {},
    )
    base.__class__ = combined
    return base
