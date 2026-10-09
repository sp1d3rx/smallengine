"""
Supplier and supplier contact API endpoints.
"""
from py4web import action, request, HTTP
from ..common import db, auth, session, require_admin as require_user


@action("api/suppliers", method=["GET"])
@action.uses(db, session, auth)
def suppliers_list():
    require_user()
    q = request.query.get("q", "").strip()
    query = db.supplier.active == True
    if q:
        query &= db.supplier.name.contains(q)
    rows = db(query).select(orderby=db.supplier.name)
    result = []
    for row in rows:
        item = row.as_dict()
        primary = db(
            (db.supplier_contact.supplier_id == row.id)
            & (db.supplier_contact.is_primary == True)
        ).select().first()
        item["primary_contact"] = primary.as_dict() if primary else None
        result.append(item)
    return dict(suppliers=result)


@action("api/suppliers", method=["POST"])
@action.uses(db, session, auth)
def suppliers_create():
    require_user()
    data = request.json or {}
    result = db.supplier.validate_and_insert(**{
        k: data.get(k) for k in [
            "name", "phone", "email", "website", "account_number",
            "terms", "default_shipping", "notes",
        ]
    })
    if result.get("errors"):
        raise HTTP(422, str(result["errors"]))
    db.commit()
    return dict(id=result["id"])


@action("api/suppliers/<supplier_id:int>", method=["GET"])
@action.uses(db, session, auth)
def suppliers_get(supplier_id):
    require_user()
    row = db.supplier[supplier_id]
    if not row:
        raise HTTP(404)
    contacts = db(db.supplier_contact.supplier_id == supplier_id).select(
        orderby=[~db.supplier_contact.is_primary, db.supplier_contact.name]
    )
    # Recent POs
    pos = db(db.purchase_order.supplier_id == supplier_id).select(
        orderby=~db.purchase_order.created_on, limitby=(0, 20)
    )
    return dict(
        supplier=row.as_dict(),
        contacts=[c.as_dict() for c in contacts],
        purchase_orders=[p.as_dict() for p in pos],
    )


@action("api/suppliers/<supplier_id:int>", method=["PUT"])
@action.uses(db, session, auth)
def suppliers_update(supplier_id):
    require_user()
    if not db.supplier[supplier_id]:
        raise HTTP(404)
    data = request.json or {}
    allowed = {"name", "phone", "email", "website", "account_number",
               "terms", "default_shipping", "notes", "active"}
    db(db.supplier.id == supplier_id).update(
        **{k: data[k] for k in data if k in allowed}
    )
    db.commit()
    return dict(ok=True)


# ── Supplier contacts ──────────────────────────────────────────────────────────

@action("api/suppliers/<supplier_id:int>/contacts", method=["POST"])
@action.uses(db, session, auth)
def contacts_create(supplier_id):
    require_user()
    if not db.supplier[supplier_id]:
        raise HTTP(404)
    data = request.json or {}
    is_primary = bool(data.get("is_primary", False))
    # If setting as primary, clear existing primary
    if is_primary:
        db(
            (db.supplier_contact.supplier_id == supplier_id)
            & (db.supplier_contact.is_primary == True)
        ).update(is_primary=False)
    result = db.supplier_contact.validate_and_insert(
        supplier_id=supplier_id,
        name=data.get("name", ""),
        title=data.get("title", ""),
        phone=data.get("phone", ""),
        email=data.get("email", ""),
        is_primary=is_primary,
        notes=data.get("notes", ""),
    )
    if result.get("errors"):
        raise HTTP(422, str(result["errors"]))
    db.commit()
    return dict(id=result["id"])


@action("api/suppliers/<supplier_id:int>/contacts/<contact_id:int>", method=["PUT"])
@action.uses(db, session, auth)
def contacts_update(supplier_id, contact_id):
    require_user()
    contact = db((db.supplier_contact.id == contact_id)
                 & (db.supplier_contact.supplier_id == supplier_id)).select().first()
    if not contact:
        raise HTTP(404)
    data = request.json or {}
    is_primary = data.get("is_primary")
    if is_primary:
        db(
            (db.supplier_contact.supplier_id == supplier_id)
            & (db.supplier_contact.is_primary == True)
        ).update(is_primary=False)
    allowed = {"name", "title", "phone", "email", "is_primary", "notes"}
    db(db.supplier_contact.id == contact_id).update(
        **{k: data[k] for k in data if k in allowed}
    )
    db.commit()
    return dict(ok=True)


@action("api/suppliers/<supplier_id:int>/contacts/<contact_id:int>", method=["DELETE"])
@action.uses(db, session, auth)
def contacts_delete(supplier_id, contact_id):
    require_user()
    db((db.supplier_contact.id == contact_id)
       & (db.supplier_contact.supplier_id == supplier_id)).delete()
    db.commit()
    return dict(ok=True)
