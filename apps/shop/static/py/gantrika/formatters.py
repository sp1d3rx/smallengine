"""Gantrika Formatters — Idiomatic domain formatting vocabulary for Python web UIs."""
from browser import window


def currency(val, default="$0.00"):
    """Format numeric amount as $X.XX or return default."""
    if val is None or val == "":
        return default
    try:
        fval = float(val)
        return f"${fval:,.2f}"
    except (ValueError, TypeError):
        return default


def short_date(iso_val, default="—"):
    """Extract YYYY-MM-DD from an ISO string or date."""
    if not iso_val:
        return default
    s = str(iso_val).strip()
    return s[:10] if len(s) >= 10 else s or default


def local_time(iso_str, default="—"):
    """Convert UTC ISO datetime string to browser's localized format."""
    if not iso_str:
        return default
    clean = str(iso_str).strip()
    # Normalize space to T  e.g. "2026-03-19 00:37:41" → "...T..."
    if len(clean) >= 19 and clean[10] == " ":
        clean = clean[:10] + "T" + clean[11:]
    if "T" in clean and not clean.endswith("Z") and "+" not in clean[10:]:
        clean += "Z"
    try:
        return window.eval(f"new Date('{clean}').toLocaleString()")
    except Exception:
        return clean[:16].replace("T", " ")


def human_days_ago(days, default="never"):
    """Convert integer days into human-friendly relative string."""
    if days is None or days == 9999 or days == "":
        return default
    try:
        d = int(days)
        if d <= 0:
            return "today"
        if d == 1:
            return "yesterday"
        return f"{d} days ago"
    except (ValueError, TypeError):
        return default


def percentage(val, decimals=1, default="0.0%"):
    """Format decimal/float as percentage string."""
    if val is None or val == "":
        return default
    try:
        return f"{float(val):.{decimals}f}%"
    except (ValueError, TypeError):
        return default


def delta_qty(delta, default="0"):
    """Format quantity delta with explicit + sign (e.g. +5, -3)."""
    if delta is None:
        return default
    try:
        d = int(delta)
        return f"+{d}" if d > 0 else str(d)
    except (ValueError, TypeError):
        return default
