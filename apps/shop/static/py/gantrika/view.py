"""Gantrika View — Component & Page Lifecycle base class."""
from browser import document
from .ui import render, render_partial

class View:
    """Base class for page views and UI components with lifecycle hooks."""
    template = ""
    target = "content"

    def __init__(self):
        self.params = {}
        self.query = {}
        self.state = {}

    @classmethod
    def render_view(cls, params=None, query=None):
        instance = cls()
        instance.params = params or {}
        instance.query = query or {}
        instance.mount()
        return instance

    def mount(self):
        """Lifecycle hook called immediately after routing match."""
        pass

    def render(self, data=None, template_id=None, target_id=None):
        """Compile and render template into DOM target."""
        tpl = template_id or self.template
        tgt = target_id or self.target
        render(tpl, data or {}, target=tgt)
        self.bind_events()

    def render_partial(self, template_id, data=None):
        """Render a sub-template into HTML string."""
        return render_partial(template_id, data or {})

    def bind_events(self):
        """Lifecycle hook called after DOM render to wire up event listeners."""
        pass

    def on_click(self, selector, handler):
        """Bind click listener to all elements matching selector."""
        for el in document.select(selector):
            el.bind("click", handler)

    def on_input(self, selector, handler):
        """Bind input listener to all elements matching selector."""
        for el in document.select(selector):
            el.bind("input", handler)

    def on_change(self, selector, handler):
        """Bind change listener to all elements matching selector."""
        for el in document.select(selector):
            el.bind("change", handler)

    def on_submit(self, selector, handler):
        """Bind submit listener to form element."""
        for el in document.select(selector):
            def _wrapped_submit(ev):
                ev.preventDefault()
                handler(ev)
            el.bind("submit", _wrapped_submit)

    def unmount(self):
        """Lifecycle teardown hook."""
        pass
