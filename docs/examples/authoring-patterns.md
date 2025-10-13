### Authoring Patterns Example

This example mirrors the demo app's Patterns page and showcases:

- State with `signal` and derived values with `computed`
- Children composition (a `Card` component)
- Cleanup via `on_cleanup` (a ticking `Timer`)

Key snippets (see demo under `examples/demo` for full code):

```python
from wybthon import h

def Card(props):
    title = props.get("title", "")
    children = props.get("children", [])
    if not isinstance(children, list):
        children = [children]
    return h("section", {"class": "card"}, h("h3", {}, title), children)
```

```python
from wybthon import Component, h, signal, computed

class NamesList(Component):
    def __init__(self, props):
        super().__init__(props)
        self.names = signal([])
        self.starts_with_a = computed(
            lambda: len([n for n in self.names.get() if str(n).lower().startswith("a")])
        )

        def make_add(name):
            return lambda _evt: self.names.set(self.names.get() + [name])

        def clear(_evt):
            self.names.set([])

        self._add_ada = make_add("Ada")
        self._add_alan = make_add("Alan")
        self._clear = clear

    def render(self):
        items = [h("li", {}, n) for n in self.names.get()]
        return h(
            "div",
            {},
            h("p", {}, f"Total: {len(self.names.get())} | Starts with A: {self.starts_with_a.get()}"),
            h("div", {},
              h("button", {"on_click": getattr(self, "_add_ada", lambda e: None)}, "+ Ada"),
              h("button", {"on_click": getattr(self, "_add_alan", lambda e: None)}, "+ Alan"),
              h("button", {"on_click": getattr(self, "_clear", lambda e: None)}, "Clear"),
            ),
            h("ul", {}, items),
        )
```

```python
from wybthon import Component, h, signal

class Timer(Component):
    def __init__(self, props):
        super().__init__(props)
        self.seconds = signal(0)

        try:
            from js import setInterval, clearInterval
            from pyodide.ffi import create_proxy

            def tick():
                self.seconds.set(self.seconds.get() + 1)

            tick_proxy = create_proxy(lambda: tick())
            interval_id = setInterval(tick_proxy, 1000)

            def cleanup():
                try:
                    clearInterval(interval_id)
                except Exception:
                    pass
                try:
                    tick_proxy.destroy()
                except Exception:
                    pass

            self.on_cleanup(cleanup)
        except Exception:
            pass

    def render(self):
        return h("div", {"class": "timer"}, f"Seconds: {self.seconds.get()}")
```

```python
from wybthon import h

def Page(_props):
    return h(
        "div",
        {},
        h(Card, {"title": "State & Derived"}, h(NamesList, {})),
        h(Card, {"title": "Cleanup"}, h(Timer, {})),
    )
```

See the guide for deeper discussion: [Authoring Patterns](../guides/authoring-patterns.md)


