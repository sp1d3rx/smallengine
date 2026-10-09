"""Gantrika — Desktop-class Python SPA Framework for Web Applications."""

from .router import router, route, Router
from .ui import Toast, Modal, render, render_partial, safe_action
from .forms import form_data, populate_form, set_form_errors, clear_form_errors
from .resource import Resource, ApiError, request
from .view import View
from .split_view import SplitPaneView
from .store import Store, store
from .formatters import currency, short_date, local_time, human_days_ago, percentage, delta_qty

__all__ = [
    "router",
    "route",
    "Router",
    "Toast",
    "Modal",
    "render",
    "render_partial",
    "safe_action",
    "form_data",
    "populate_form",
    "set_form_errors",
    "clear_form_errors",
    "Resource",
    "ApiError",
    "request",
    "View",
    "SplitPaneView",
    "Store",
    "store",
    "currency",
    "short_date",
    "local_time",
    "human_days_ago",
    "percentage",
    "delta_qty",
]
