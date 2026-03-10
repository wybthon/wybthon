### Authoring Patterns

This guide shows how to author components in Wybthon using the `@component` decorator, traditional function components, and class components. It focuses on props, state with `signal`/`computed`/`effect`, children composition, cleanup, and context.

#### `@component` decorator (recommended)

The `@component` decorator lets you define props as keyword arguments,
making components self-documenting and type-safe:

```python
from wybthon import component, h2

@component
def Hello(name: str = "world", greeting: str = "Hello"):
    return h2(f"{greeting}, {name}!")
```

- Props become regular Python parameters with defaults and type annotations.
- Missing props use the default value from the signature.
- Extra props not in the signature are ignored.

Children handling with `@component`:

```python
from wybthon import component, h3, section

@component
def Card(title: str = "", children=None):
    kids = children if isinstance(children, list) else ([children] if children else [])
    return section(h3(title), *kids, class_name="card")
```

Direct calls return VNodes for composition without `h()`:

```python
Card("child text", title="My Card")  # positional args become children
Counter(initial=5)                   # keyword args become props
```

Stateful component with hooks:

```python
from wybthon import button, component, div, p, use_state, use_effect

@component
def Counter(initial: int = 0):
    count, set_count = use_state(initial)

    def on_mount():
        print(f"Counter mounted with count: {count}")

    use_effect(on_mount, [])

    return div(
        p(f"Count: {count}"),
        button("+1", on_click=lambda e: set_count(lambda c: c + 1)),
        class_name="counter",
    )
```

#### Traditional function components

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

        comp = effect(lambda: print("count:", self.count.get()))
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

With `@component`, props and defaults are built into the function signature:

```python
@component
def Avatar(src: str = "", alt: str = "avatar", size: int = 48):
    return img(src=src, alt=alt, width=str(size), height=str(size))
```

With traditional functions, prefer `props.get("key", default)` when reading optional values. For required props, consider simple guards at the top of `render`.

#### Passing and using children

With `@component`, children come via the `children` parameter:

```python
@component
def Layout(children=None):
    kids = children if isinstance(children, list) else ([children] if children else [])
    return div(*kids, class_name="layout")
```

With traditional functions, the VDOM passes children via `props["children"]` for component tags. Normalize to a list when rendering:

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
from wybthon import Provider, component, h, use_context
from wybthon.context import create_context

Theme = create_context("light")

@component
def ThemeLabel():
    return h("span", {}, f"Theme: {use_context(Theme)}")

@component
def Layout(children=None):
    kids = children if isinstance(children, list) else ([children] if children else [])
    return h("div", {}, h(Provider, {"context": Theme, "value": "dark"}, kids))
```

#### Choosing between styles

- Use **`@component` with hooks** for most components — concise, type-safe, composable.
- Use **traditional function components** for simple wrappers or when migrating existing code.
- Use **class components** when you need reactive signals with fine-grained control, complex lifecycle management, or when porting patterns from React class components.

All three styles interoperate seamlessly and can be composed together.

#### Patterns checklist

- Use `@component` for new function components with typed props.
- Accept `children` and pass them through when building layout components.
- Store signals on `self` in class components; avoid re-creating them during `render`.
- Use `effect` for side-effects; dispose in `on_cleanup`.
- Keep events simple and avoid catching errors unless you can handle them.

#### Larger examples

1) Composition via children (`@component`)

```python
from wybthon import component, h, h3, p, section

@component
def Card(title: str = "", children=None):
    kids = children if isinstance(children, list) else ([children] if children else [])
    return section(h3(title), *kids, class_name="card")

@component
def Page():
    return div(
        Card(p("Card body via children"), title="Composition"),
    )
```

2) State and derived values (class component with `signal` + `computed`)

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

3) Cleanup and lifecycles (`@component` with hooks)

```python
from wybthon import component, div, use_effect, use_state

@component
def Timer():
    seconds, set_seconds = use_state(0)

    def setup():
        from js import setInterval, clearInterval
        from pyodide.ffi import create_proxy

        proxy = create_proxy(lambda: set_seconds(lambda s: s + 1))
        tid = setInterval(proxy, 1000)

        def cleanup():
            clearInterval(tid)
            proxy.destroy()
        return cleanup

    use_effect(setup, [])

    return div(f"Seconds: {seconds}", class_name="timer")
```

Putting it together:

```python
from wybthon import component, div, h

@component
def Page():
    return div(
        Card(h(NamesList, {}), title="State & Derived"),
        Card(h(Timer, {}), title="Cleanup"),
    )
```

See the demo app "Patterns" page for a working version of these examples.
