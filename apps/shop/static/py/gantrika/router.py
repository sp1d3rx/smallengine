"""Gantrika Router — Client-side declarative URL hash router for Brython SPAs."""
import re
from browser import document, window

class Route:
    def __init__(self, pattern, handler, name=None, meta=None):
        self.pattern = pattern.strip("/")
        self.handler = handler
        self.name = name or pattern
        self.meta = meta or {}
        self.regex, self.param_specs = self._compile(self.pattern)

    def _compile(self, pattern):
        """Compile route pattern with <name:type> or <name> parameters to regex."""
        param_specs = []
        if not pattern:
            return re.compile(r"^$"), []

        parts = pattern.split("/")
        regex_parts = []

        for part in parts:
            if part.startswith("<") and part.endswith(">"):
                spec = part[1:-1]
                if ":" in spec:
                    pname, ptype = spec.split(":", 1)
                else:
                    pname, ptype = spec, "str"

                param_specs.append((pname, ptype))

                if ptype == "int":
                    regex_parts.append(r"(?P<" + pname + r">\d+)")
                elif ptype == "float":
                    regex_parts.append(r"(?P<" + pname + r">\d+(?:\.\d+)?)")
                else:
                    regex_parts.append(r"(?P<" + pname + r">[^/?#]+)")
            else:
                regex_parts.append(re.escape(part))

        regex_str = "^" + "/".join(regex_parts) + "$"
        return re.compile(regex_str), param_specs

    def match(self, path):
        """Match clean path against compiled regex and return coerced params dict."""
        clean = path.strip("/")
        m = self.regex.match(clean)
        if not m:
            return None

        raw_params = m.groupdict()
        coerced = {}
        for pname, ptype in self.param_specs:
            val = raw_params.get(pname)
            if val is not None:
                if ptype == "int":
                    coerced[pname] = int(val)
                elif ptype == "float":
                    coerced[pname] = float(val)
                else:
                    coerced[pname] = str(val)
        return coerced


class Router:
    def __init__(self):
        self.routes = []
        self.before_hooks = []
        self.after_hooks = []
        self.not_found_handler = None
        self.error_handler = None
        self.current_route = None
        self.current_path = None
        self.current_params = {}
        self.current_query = {}

    def add(self, pattern, handler, name=None, meta=None):
        """Register a route pattern and handler."""
        route_obj = Route(pattern, handler, name=name, meta=meta)
        self.routes.append(route_obj)
        return route_obj

    def before_each(self, hook_fn):
        """Add navigation guard hook fn(to_path, params, query) returning False to cancel."""
        self.before_hooks.append(hook_fn)

    def after_each(self, hook_fn):
        """Add post-navigation hook fn(to_path, params, query)."""
        self.after_hooks.append(hook_fn)

    def on_not_found(self, handler):
        self.not_found_handler = handler

    def on_error(self, handler):
        self.error_handler = handler

    def parse_query_string(self, qs):
        """Parse query string into a dict."""
        params = {}
        if not qs:
            return params
        for pair in qs.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                k = k.replace("+", " ")
                v = v.replace("+", " ")
                params[k] = v
            elif pair:
                params[pair] = True
        return params

    def navigate(self, path):
        """Change URL hash to navigate."""
        if not path.startswith("#"):
            path = "#" + (path if path.startswith("/") else "/" + path)
        window.location.hash = path

    def dispatch(self, hash_url=None):
        """Dispatch route from current window hash or provided string."""
        if hash_url is None:
            hash_url = window.location.hash or "#/"

        raw_path = hash_url[1:] if hash_url.startswith("#") else hash_url
        if not raw_path:
            raw_path = "/"

        qs = ""
        path = raw_path
        if "?" in raw_path:
            path, qs = raw_path.split("?", 1)

        query_params = self.parse_query_string(qs)
        clean_path = path.strip("/")

        # Run before hooks
        for hook in self.before_hooks:
            if hook(path, query_params) is False:
                return

        # Match route
        matched_route = None
        matched_params = {}

        for r in self.routes:
            params = r.match(clean_path)
            if params is not None:
                matched_route = r
                matched_params = params
                break

        self.current_path = path
        self.current_route = matched_route
        self.current_params = matched_params
        self.current_query = query_params

        self.update_nav_links(path)

        try:
            if matched_route:
                handler = matched_route.handler
                if hasattr(handler, "render_view"):
                    handler.render_view(params=matched_params, query=query_params)
                elif callable(handler):
                    handler(**matched_params)
            else:
                if self.not_found_handler:
                    self.not_found_handler(path)
                else:
                    document["content"].html = (
                        f"<section class='page'><h1>404</h1><p>Page '{path}' not found.</p></section>"
                    )
        except Exception as err:
            import traceback
            tb = traceback.format_exc()
            if self.error_handler:
                self.error_handler(err, tb)
            else:
                print(f"Router error on '{path}': {err}\n{tb}")
                document["content"].html = (
                    f"<section class='page'><p style='color:red'>Error: {err}</p>"
                    f"<pre style='font-size:.75rem'>{tb}</pre></section>"
                )

        # Run after hooks
        for hook in self.after_hooks:
            hook(path, matched_params, query_params)

    def update_nav_links(self, path):
        """Update active classes on main navigation links and dropdown parents."""
        formatted_path = "/" + path.strip("/") if path.strip("/") else "/"

        for link in document.select(".main-nav a"):
            nav_path = link.getAttribute("data-nav") or "/"
            if formatted_path == nav_path or (nav_path != "/" and formatted_path.startswith(nav_path)):
                link.classList.add("active")
            else:
                link.classList.remove("active")

        for dropdown in document.select(".nav-dropdown"):
            nav_path = dropdown.getAttribute("data-nav") or ""
            if nav_path and (formatted_path == nav_path or formatted_path.startswith(nav_path)):
                dropdown.classList.add("active")
            else:
                dropdown.classList.remove("active")

    def init_dropdowns(self):
        """Wire up hover-leave resets and instant collapse on dropdown item click."""
        for dropdown in document.select(".nav-dropdown"):
            def _on_leave(ev, dd=dropdown):
                dd.classList.remove("collapsed")
            dropdown.bind("mouseleave", _on_leave)

            for link in dropdown.select(".nav-dropdown-menu a"):
                def _on_click(ev, dd=dropdown):
                    dd.classList.add("collapsed")
                link.bind("click", _on_click)

    def start(self):
        """Attach hashchange listener and dispatch initial route."""
        self.init_dropdowns()
        window.addEventListener("hashchange", lambda ev: self.dispatch())
        self.dispatch()


# Global default router instance
router = Router()

def route(pattern, name=None, meta=None):
    """Decorator to register a function or View class with the global router."""
    def decorator(fn_or_cls):
        router.add(pattern, fn_or_cls, name=name, meta=meta)
        return fn_or_cls
    return decorator
