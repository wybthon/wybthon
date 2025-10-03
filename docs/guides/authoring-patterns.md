### Authoring Patterns

This guide shows how to author components in Wybthon using both function and class styles. It focuses on props, state with `signal`/`computed`/`effect`, children composition, cleanup, and context.

#### Function components

Use plain Python callables that receive a `props` dict and return a VNode via `h(...)`.

```python
from wybthon import h

def Hello(props):
    name = props.get("name", "world")
    return h("div", {"class": "hello"}, f"Hello, {name}")
```

- Props are read-only; compute derived values inline or via `computed` when expensive.
- To accept children, read `props.get("children", [])`. The VDOM passes children via props for components.

Children handling:

```python
def Card(props):
    title = props.get("title", "")
    children = props.get("children", [])
    return h("section", {"class": "card"}, h("h3", {}, title), children)
```

Side effects and subscriptions are typically modeled in class components (see below). Function components are best for presentational/stateless pieces.

#### Class components

Subclass `Component` to encapsulate state and lifecycles.

```python
from wybthon import Component, h, signal, effect, on_effect_cleanup

class Counter(Component):
    def __init__(self, props):
        super().__init__(props)
        self.count = signal(0)

        def inc(_evt):
            self.count.set(self.count.get() + 1)

        self._inc = inc

        # Example: reactive side effect
        comp = effect(lambda: print("count:", self.count.get()))
        # Ensure cleanup on unmount
        on_effect_cleanup(comp, lambda: print("effect disposed"))
        self.on_cleanup(lambda: comp.dispose())

    def render(self):
        return h(
            "div",
            {"class": "counter"},
            h("p", {}, f"Count: {self.count.get()}"),
            h("button", {"on_click": getattr(self, "_inc", lambda e: None)}, "Increment"),
        )
```

- State: store `signal` instances as attributes. Read with `.get()` during render.
- Events: pass bound methods or closures via `on_click`, `on_input`, etc.
- Cleanup: register teardown work with `on_cleanup(fn)` so it runs on unmount.
- Updates: `on_update(prev_props)` fires after a prop change and diff is applied.

#### Props and defaults

Prefer `props.get("key", default)` when reading optional values. For required props, consider simple guards at the top of `render`.

#### Passing and using children

The VDOM passes children via `props["children"]` for component tags. Normalize to a list when rendering:

```python
def Layout(props):
    children = props.get("children", [])
    if not isinstance(children, list):
        children = [children]
    return h("div", {"class": "layout"}, children)
```

#### Context

Provide values with `Provider` and read with `use_context`.

```python
from wybthon import Provider, h, use_context
from wybthon.context import create_context

Theme = create_context("light")

def ThemeLabel(_props):
    return h("span", {}, f"Theme: {use_context(Theme)}")

def Layout(props):
    children = props.get("children", [])
    return h("div", {}, h(Provider, {"context": Theme, "value": "dark"}, children))
```

#### Choosing between function and class

- Use **function components** for pure UI composition without local reactive state or lifecycle needs.
- Use **class components** when you need reactive state, effects, cleanup, or lifecycle hooks.

Both interoperate seamlessly and can be composed together.

#### Patterns checklist

- Read props defensively with defaults.
- Store signals on `self` in class components; avoid re-creating them during `render`.
- Use `effect` for side-effects; dispose in `on_cleanup`.
- Accept `children` and pass them through when building layout components.
- Keep events simple and avoid catching errors unless you can handle them.
