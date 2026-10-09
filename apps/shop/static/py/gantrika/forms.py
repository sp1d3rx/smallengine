"""Gantrika Forms — Two-way form serialization, validation display, and element binding."""
from browser import document

def _resolve_element(target):
    if isinstance(target, str):
        return document.select_one(target) if hasattr(document, "select_one") else document.querySelector(target)
    return target


def form_data(target, coerce=True):
    """Extract form inputs, selects, and textareas into a Python dict.
    
    Coerces number inputs, converts empty strings to empty strings or handles checkboxes.
    """
    form_el = _resolve_element(target)
    if not form_el:
        return {}

    data = {}
    inputs = form_el.select("input, select, textarea")

    for field in inputs:
        name = field.getAttribute("name")
        if not name:
            continue

        tag = field.tagName.lower()
        input_type = (field.getAttribute("type") or "text").lower() if tag == "input" else tag

        if input_type == "checkbox":
            val = field.checked
        elif input_type == "radio":
            if field.checked:
                data[name] = field.value
            continue
        elif input_type == "number":
            raw_val = field.value.strip() if field.value is not None else ""
            if not raw_val:
                val = None
            elif "." in raw_val:
                try:
                    val = float(raw_val)
                except ValueError:
                    val = None
            else:
                try:
                    val = int(raw_val)
                except ValueError:
                    val = None
        else:
            raw_val = field.value
            val = raw_val.strip() if isinstance(raw_val, str) else raw_val

        data[name] = val

    return data


def populate_form(target, data):
    """Populate a form with key-value data from a dictionary."""
    form_el = _resolve_element(target)
    if not form_el or not isinstance(data, dict):
        return

    for name, value in data.items():
        fields = form_el.select(f"[name='{name}']")
        for field in fields:
            tag = field.tagName.lower()
            input_type = (field.getAttribute("type") or "text").lower() if tag == "input" else tag

            if input_type == "checkbox":
                field.checked = bool(value)
            elif input_type == "radio":
                field.checked = (str(field.value) == str(value))
            else:
                field.value = "" if value is None else str(value)


def set_form_errors(target, errors):
    """Display inline error messages on form fields."""
    form_el = _resolve_element(target)
    if not form_el or not isinstance(errors, dict):
        return

    clear_form_errors(form_el)

    for name, err_msg in errors.items():
        fields = form_el.select(f"[name='{name}']")
        if fields:
            field = fields[0]
            field.classList.add("input-error")
            parent = field.closest(".field") or field.parentElement
            if parent:
                err_span = document.createElement("span")
                err_span.className = "field-error-msg"
                err_span.text = str(err_msg)
                parent <= err_span


def clear_form_errors(target):
    """Remove all validation error indicators from a form."""
    form_el = _resolve_element(target)
    if not form_el:
        return

    for el in form_el.select(".input-error"):
        el.classList.remove("input-error")
    for el in form_el.select(".field-error-msg"):
        el.remove()
