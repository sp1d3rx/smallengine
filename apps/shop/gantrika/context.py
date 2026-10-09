"""Gantrika Context — Base domain context service layer."""
from contextlib import contextmanager

class ValidationError(Exception):
    def __init__(self, message, errors=None):
        self.message = message
        self.errors = errors or {}
        super().__init__(message)


class NotFoundError(Exception):
    pass


class BusinessRuleError(Exception):
    pass


class BaseContext:
    """Base class for domain service contexts isolating business rules from HTTP controllers."""
    def __init__(self, db, auth=None):
        self.db = db
        self.auth = auth

    @contextmanager
    def transaction(self):
        """Context manager providing an atomic database transaction boundary."""
        try:
            yield
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def validate_required(self, data, *fields):
        """Ensure all required fields are present and non-empty."""
        errors = {}
        for f in fields:
            val = data.get(f)
            if val is None or (isinstance(val, str) and not val.strip()):
                errors[f] = f"{f.replace('_', ' ').title()} is required."
        if errors:
            raise ValidationError("Validation failed", errors=errors)

    def filter_allowed(self, data, allowed_fields):
        """Return a copy of data containing only explicitly allowed fields."""
        return {k: v for k, v in data.items() if k in allowed_fields}
