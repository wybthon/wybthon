### Authoring Patterns

This guide shows how to author components in Wybthon using the `@component` decorator and traditional function components. It focuses on props, state with `create_signal`/`create_effect`/`create_memo`, children composition, cleanup, and context.

#### `@component` decorator (recommended)

The `@component` decorator lets you define props as keyword arguments,
making components self-documenting and type-safe:

```python
from wybthon import component, h2

@component
def Hello(name: str = "world", greeting: str = "Hello"):
    return h2(f"{greeting}, {name}!")
```

- Props become regular Python parameters with defaults and type annotations. Each is a **plain value** (not a getter).
- Missing props use the default value from the signature.
- Extra props not in the signature are ignored.

Children handling with `@component` — the `children` parameter is a **plain** vnode, list, or `None` (import the `children()` *helper* from `wybthon` under another name if you need memoized reactive resolution; see [Reactivity](../api/reactivity.md)):

```python
from wybthon import component, h3, section

@component
def Card(title: str = "", children=None):
    kids = children or []
    if not isinstance(kids, list):
        kids = [kids]
    return section(h3(title), *kids, class_name="card")
```

Direct calls return VNodes for composition without `h()`:

```python
Card("child text", title="My Card")  # positional args become children
Counter(initial=5)                   # keyword args become props
```

Stateful component with signals:

```python
from wybthon import button, component, create_signal, div, on_mount, p

@component
def Counter(initial: int = 0):
    count, set_count = create_signal(initial)

    on_mount(lambda: print(f"Counter mounted with count: {count()}"))

    def render():
        return div(
            p(f"Count: {count()}"),
            button("+1", on_click=lambda e: set_count(count() + 1)),
            class_name="counter",
        )
    return render
```

#### Traditional function components

Use plain Python callables that receive a `props` dict and return a VNode via `h(...)`.

```python
from wybthon import h

def Hello(props):
    name = props.get("name", "world")
    return h("div", {"class": "hello"}, f"Hello, {name}")
```

- Props are read-only; compute derived values inline or via `create_memo` when expensive.
- To accept children, read `props.get("children", [])`. The VDOM passes children via props for components.

Children handling:

```python
def Card(props):
    title = props.get("title", "")
    children = props.get("children", [])
    return h("section", {"class": "card"}, h("h3", {}, title), children)
```

#### Props and defaults

With `@component`, props and defaults are built into the function signature:

```python
from wybthon import component, img

@component
def Avatar(src: str = "", alt: str = "avatar", size: int = 48):
    return img(src=src, alt=alt, width=str(size), height=str(size))
```

With traditional functions, prefer `props.get("key", default)` when reading optional values. For required props, consider simple guards at the top of `render`.

#### Passing and using children

With `@component`, children come via the `children` parameter as a plain value:

```python
from wybthon import component, div

@component
def Layout(children=None):
    kids = children or []
    if not isinstance(kids, list):
        kids = [kids]
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
    kids = children or []
    if not isinstance(kids, list):
        kids = [kids]
    return h("div", {}, h(Provider, {"context": Theme, "value": "dark"}, kids))
```

#### Choosing between styles

- Use **`@component` with signals** for most components — concise, type-safe, composable.
- Use **traditional function components** for simple wrappers or when migrating existing code.

Both styles interoperate seamlessly and can be composed together.

#### Patterns checklist

- Use `@component` for new function components with typed props.
- Accept `children` and pass them through when building layout components.
- Use `create_effect` for side-effects; clean up with `on_cleanup`.
- Keep events simple and avoid catching errors unless you can handle them.

#### Larger examples

1) Composition via children (`@component`)

```python
from wybthon import component, div, h3, p, section

@component
def Card(title: str = "", children=None):
    kids = children or []
    if not isinstance(kids, list):
        kids = [kids]
    return section(h3(title), *kids, class_name="card")

@component
def Page():
    return div(
        Card(p("Card body via children"), title="Composition"),
    )
```

2) State and derived values (`@component` with `create_signal` + `create_memo`)

```python
from wybthon import button, component, create_memo, create_signal, div, h, p, ul

@component
def NamesList():
    names, set_names = create_signal([])
    starts_with_a = create_memo(
        lambda: len([n for n in names() if str(n).lower().startswith("a")])
    )

    def make_add(name):
        return lambda _evt: set_names(names() + [name])

    def clear(_evt):
        set_names([])

    def render():
        items = [h("li", {}, n) for n in names()]
        return div(
            p(f"Total: {len(names())} | Starts with A: {starts_with_a()}"),
            div(
                button("+ Ada", on_click=make_add("Ada")),
                button("+ Alan", on_click=make_add("Alan")),
                button("Clear", on_click=clear),
            ),
            ul(*items),
        )
    return render
```

3) Cleanup and lifecycles (`@component` with signals)

```python
from wybthon import component, create_signal, div, on_cleanup, on_mount

@component
def Timer():
    seconds, set_seconds = create_signal(0)

    def start():
        from js import setInterval, clearInterval
        from pyodide.ffi import create_proxy

        proxy = create_proxy(lambda: set_seconds(seconds() + 1))
        tid = setInterval(proxy, 1000)

        on_cleanup(lambda: (clearInterval(tid), proxy.destroy()))

    on_mount(start)

    def render():
        return div(f"Seconds: {seconds()}", class_name="timer")
    return render
```

Putting it together:

```python
from wybthon import component, div, h

@component
def Page():
    return div(
        h(Card, {"title": "State & Derived"}, h(NamesList, {})),
        h(Card, {"title": "Cleanup"}, h(Timer, {})),
    )
```

See the demo app "Patterns" page for a working version of these examples.
