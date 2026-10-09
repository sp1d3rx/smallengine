"""Gantrika Server Response — Standard JSON envelope helpers."""
from py4web import response

def json_ok(data=None, meta=None, status=200):
    """Return a successful JSON response with a standard envelope."""
    response.status = status
    payload = {
        "status": "success",
        "data": data if data is not None else {}
    }
    if meta:
        payload["meta"] = meta
    return payload


def json_error(message, status=400, errors=None):
    """Return a structured error response with status code."""
    response.status = status
    payload = {
        "status": "error",
        "error": str(message),
        "errors": errors or {}
    }
    return payload


def json_paginated(items, total, page=1, page_size=50):
    """Return paginated list payload."""
    return json_ok(
        data=items,
        meta={
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 1
        }
    )
