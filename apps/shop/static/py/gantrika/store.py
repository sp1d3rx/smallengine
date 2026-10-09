"""Gantrika Store — Centralized state store and event emitter."""

class Store:
    def __init__(self, initial_state=None):
        self._state = initial_state or {}
        self._listeners = {}
        self._events = {}

    def get(self, key, default=None):
        return self._state.get(key, default)

    def set(self, key, value):
        old_value = self._state.get(key)
        self._state[key] = value
        if old_value != value:
            self._notify(key, value, old_value)

    def update(self, mapping):
        for k, v in mapping.items():
            self.set(k, v)

    def subscribe(self, key, callback):
        """Listen for changes on a specific state key or '*' for any change."""
        if key not in self._listeners:
            self._listeners[key] = []
        self._listeners[key].append(callback)

        def unsubscribe():
            if key in self._listeners and callback in self._listeners[key]:
                self._listeners[key].remove(callback)
        return unsubscribe

    def _notify(self, key, new_val, old_val):
        for cb in self._listeners.get(key, []):
            cb(new_val, old_val)
        for cb in self._listeners.get("*", []):
            cb(key, new_val, old_val)

    def on(self, event_name, callback):
        """Register an event listener."""
        if event_name not in self._events:
            self._events[event_name] = []
        self._events[event_name].append(callback)

        def off():
            if event_name in self._events and callback in self._events[event_name]:
                self._events[event_name].remove(callback)
        return off

    def emit(self, event_name, *args, **kwargs):
        """Emit a named event to all registered listeners."""
        for cb in self._events.get(event_name, []):
            cb(*args, **kwargs)


# Global default store instance
store = Store()
