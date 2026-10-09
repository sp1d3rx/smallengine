"""Gantrika Resource — Declarative REST API client and HTTP request bridge."""
import json
from browser import ajax, window

class ApiError(Exception):
    def __init__(self, status, message, errors=None):
        self.status = status
        self.message = message
        self.errors = errors or {}
        super().__init__(f"API Error {status}: {message}")


def request(method, url, data=None, params=None):
    """Execute a synchronous HTTP request and parse JSON response or raise ApiError."""
    if params:
        query_parts = []
        for k, v in params.items():
            if v is not None:
                query_parts.append(f"{k}={v}")
        if query_parts:
            joiner = "&" if "?" in url else "?"
            url += joiner + "&".join(query_parts)

    req = ajax.ajax()
    req.open(method.upper(), url, False)
    req.set_header("X-Requested-With", "XMLHttpRequest")
    if data is not None:
        req.set_header("Content-Type", "application/json")
        body = json.dumps(data)
    else:
        body = ""

    req.send(body)

    # Parse response
    result = {}
    raw_text = req.text or ""
    if raw_text:
        try:
            result = json.loads(raw_text)
        except Exception:
            result = {"raw": raw_text}

    if 200 <= req.status < 300:
        return result if isinstance(result, (dict, list)) else {"data": result}
    else:
        if req.status >= 500:
            msg = f"Server error ({req.status}) — check server logs"
        elif isinstance(result, dict):
            msg = result.get("error") or result.get("message") or f"Server returned HTTP {req.status}"
        else:
            msg = f"Server returned HTTP {req.status}"
        errors = result.get("errors") if isinstance(result, dict) else {}
        raise ApiError(req.status, str(msg), errors)


class Resource:
    """Represents a RESTful API resource collection."""
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")

    def list(self, **params):
        """GET /resource?[params]"""
        return request("GET", self.base_url, params=params)

    def get(self, record_id, **params):
        """GET /resource/{id}?[params]"""
        return request("GET", f"{self.base_url}/{record_id}", params=params)

    def create(self, data, **params):
        """POST /resource"""
        return request("POST", self.base_url, data=data, params=params)

    def update(self, record_id, data, **params):
        """PUT /resource/{id}"""
        return request("PUT", f"{self.base_url}/{record_id}", data=data, params=params)

    def patch(self, record_id, data, **params):
        """PATCH /resource/{id}"""
        return request("PATCH", f"{self.base_url}/{record_id}", data=data, params=params)

    def delete(self, record_id, **params):
        """DELETE /resource/{id}"""
        return request("DELETE", f"{self.base_url}/{record_id}", params=params)

    def action(self, record_id_or_none, action_name, data=None, method="POST", **params):
        """Custom RPC or sub-resource action on a resource."""
        if record_id_or_none is not None:
            url = f"{self.base_url}/{record_id_or_none}/{action_name.strip('/')}"
        else:
            url = f"{self.base_url}/{action_name.strip('/')}"
        return request(method, url, data=data, params=params)
