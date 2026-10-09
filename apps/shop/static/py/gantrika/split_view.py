"""Gantrika SplitPaneView — Master-detail two-column desktop workbench component."""
from browser import document, window
from .view import View

class SplitPaneView(View):
    """Base class for two-pane master/detail workspace pages.
    
    Provides built-in debounced live search, row selection state, and detail panel orchestration.
    """
    search_selector = "#search-input"
    list_container_selector = "#list-items"
    detail_container_selector = "#detail-panel"
    item_selector = ".list-item"
    debounce_ms = 300

    def __init__(self):
        super().__init__()
        self.selected_id = None
        self._search_timer = None

    def mount(self):
        """Default mount: renders shell and checks if detail ID is present in params."""
        self.render_shell()
        target_id = self.params.get("id")
        if target_id:
            self.select_item(target_id)

    def render_shell(self):
        """Render the split-pane shell."""
        self.render()

    def bind_events(self):
        """Bind search input debouncer and new button handlers."""
        search_el = document.querySelector(self.search_selector)
        if search_el:
            search_el.focus()
            def _on_input(ev):
                query = ev.target.value.strip()
                if self._search_timer is not None:
                    window.clearTimeout(self._search_timer)
                self._search_timer = window.setTimeout(lambda: self.on_search(query), self.debounce_ms)
            search_el.bind("input", _on_input)

    def on_search(self, query):
        """Override to handle search input."""
        pass

    def select_item(self, item_id):
        """Select an item, highlight its row, and load its detail panel."""
        self.selected_id = item_id
        self.highlight_selected(item_id)
        self.load_detail(item_id)

    def highlight_selected(self, item_id):
        """Update .selected CSS class across list rows."""
        for item in document.select(self.item_selector):
            raw_id = item.getAttribute("data-id")
            if raw_id and str(raw_id) == str(item_id):
                item.classList.add("selected")
            else:
                item.classList.remove("selected")

    def load_detail(self, item_id):
        """Override to fetch and render detail panel."""
        pass
