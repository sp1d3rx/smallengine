"""Gantrika UI — Modals, Toasts, Confirm Dialogs, and Handlebars Template compilation."""
import json
from browser import document, window

Handlebars = window.Handlebars

# Register default helpers once
window.eval("""
  if (window.Handlebars) {
    Handlebars.registerHelper('eq', function(a, b) { return a === b; });
    Handlebars.registerHelper('neq', function(a, b) { return a !== b; });
    Handlebars.registerHelper('or', function(a, b) { return a || b; });
    Handlebars.registerHelper('and', function(a, b) { return !!(a && b); });
  }
""")


def get_template(tpl_id):
    """Return raw text of a <script type='text/x-handlebars-template'> block."""
    el = document.getElementById(tpl_id)
    return el.text if el else ""


def render(tpl_id, data=None, target="content"):
    """Compile and render a Handlebars template into a DOM element (defaults to #content)."""
    data = data or {}
    tpl = get_template(tpl_id)
    target_el = document[target] if isinstance(target, str) and target in document else document.querySelector(target)

    if not tpl:
        if target_el:
            target_el.html = f"<p class='loading'>Template '{tpl_id}' not found.</p>"
        return

    js_data = window.JSON.parse(json.dumps(data))
    compiled = Handlebars.compile(tpl)
    if target_el:
        target_el.html = compiled(js_data)


def render_partial(tpl_id, data=None):
    """Return rendered HTML string for a Handlebars template."""
    data = data or {}
    tpl = get_template(tpl_id)
    if not tpl:
        return ""
    js_data = window.JSON.parse(json.dumps(data))
    compiled = Handlebars.compile(tpl)
    return str(compiled(js_data))


class Toast:
    """Feedback alerts manager."""
    @staticmethod
    def show(message, kind="info", duration=4000):
        el = document.getElementById("toast")
        if not el:
            return
        el.className = f"toast {kind}"
        el.html = str(message)

        def _hide(ev=None):
            el.className = "toast hidden"

        window.setTimeout(_hide, duration)

    @classmethod
    def success(cls, message, duration=4000):
        cls.show(message, "success", duration)

    @classmethod
    def error(cls, message, duration=5000):
        cls.show(message, "error", duration)

    @classmethod
    def info(cls, message, duration=4000):
        cls.show(message, "info", duration)

    @classmethod
    def warning(cls, message, duration=4500):
        cls.show(message, "warning", duration)


class Modal:
    """Layered modal dialog and confirmation dialog manager."""
    @staticmethod
    def show(title, body_html, wide=False, on_close=None):
        existing = document.getElementById("modal-backdrop")
        if existing:
            existing.remove()

        width_style = "width:min(720px,95vw)" if wide else ""
        backdrop = document.createElement("div")
        backdrop.id = "modal-backdrop"
        backdrop.className = "modal-backdrop"
        backdrop.html = f"""
        <div class='modal' style='{width_style}'>
          <div class='modal-header'>
            <h2>{title}</h2>
            <button class='modal-close' id='modal-close-btn' type='button'>&times;</button>
          </div>
          <div id='modal-body'>{body_html}</div>
        </div>
        """
        document.body <= backdrop

        def _close_if_backdrop(ev):
            if ev.target.id == "modal-backdrop":
                Modal.close()
                if on_close:
                    on_close()

        backdrop.bind("click", _close_if_backdrop)

        close_btn = document.getElementById("modal-close-btn")
        if close_btn:
            def _close_btn_click(ev):
                Modal.close()
                if on_close:
                    on_close()
            close_btn.bind("click", _close_btn_click)

        return backdrop

    @staticmethod
    def close():
        el = document.getElementById("modal-backdrop")
        if el:
            el.remove()

    @staticmethod
    def confirm(title, message, on_confirm, confirm_text="Confirm", cancel_text="Cancel", danger=False):
        btn_class = "btn-danger" if danger else "btn-primary"
        body_html = f"""
        <p style='margin-bottom:1.5rem'>{message}</p>
        <div style='display:flex; justify-content:flex-end; gap:0.5rem;'>
          <button type='button' class='btn btn-ghost' id='modal-confirm-cancel'>{cancel_text}</button>
          <button type='button' class='btn {btn_class}' id='modal-confirm-ok'>{confirm_text}</button>
        </div>
        """
        Modal.show(title, body_html)

        def _cancel(ev):
            Modal.close()

        def _ok(ev):
            Modal.close()
            if callable(on_confirm):
                on_confirm()

        document.getElementById("modal-confirm-cancel").bind("click", _cancel)
        document.getElementById("modal-confirm-ok").bind("click", _ok)


def safe_action(success_msg=None, on_success=None, close_modal=False):
    """Decorator for async or synchronous DOM event handlers that traps ApiError and displays toast feedback."""
    def decorator(fn):
        def wrapper(evt=None, *args, **kwargs):
            if evt and hasattr(evt, "preventDefault"):
                evt.preventDefault()
            try:
                result = fn(evt, *args, **kwargs)
                if close_modal:
                    Modal.close()
                if success_msg:
                    Toast.success(success_msg)
                if callable(on_success):
                    on_success(result)
                return result
            except Exception as err:
                msg = getattr(err, "message", str(err))
                Toast.error(f"Error: {msg}")
        return wrapper
    return decorator

