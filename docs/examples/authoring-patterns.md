### Authoring Patterns Example

This example mirrors the demo app's Patterns page and showcases:

- State with `create_signal` and derived values with `create_memo`
- Children composition (a `Card` component)
- Reactive list rendering with `For`
- Reactive expressions with `dynamic`
- Cleanup via `on_cleanup` (a ticking `Timer`)

Key snippets (see the demo under `examples/demo` for full code):

```python
from wybthon import component, h3, section, untrack

@component
def Card(title="", children=None):
    kids = untrack(children) if callable(children) else children
    if kids is None:
        kids = []
    if not isinstance(kids, list):
        kids = [kids]
    return section(h3(title), *kids, class_="card")
```

```python
from wybthon import (
    For, button, component, create_memo, create_signal, div, dynamic, li, p, ul,
)

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

    return div(
        p(dynamic(lambda: f"Total: {len(names())} | Starts with A: {starts_with_a()}")),
        div(
            button("+ Ada", on_click=make_add("Ada")),
            button("+ Alan", on_click=make_add("Alan")),
            button("Clear", on_click=clear),
        ),
        ul(For(each=names, children=lambda n, _i: li(n))),
    )
```

```python
from wybthon import component, create_signal, div, dynamic, on_cleanup, on_mount

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

    return div(dynamic(lambda: f"Seconds: {seconds()}"), class_="timer")
```

```python
from wybthon import component, div, h

@component
def Page():
    return div(
        h(Card, {"title": "State & Derived"}, h(NamesList, {})),
        h(Card, {"title": "Cleanup"}, h(Timer, {})),
    )
```

See the guide for deeper discussion: [Authoring Patterns](../guides/authoring-patterns.md)

## Next steps

- Read [Components](../concepts/components.md) and [Lifecycle and Ownership](../concepts/lifecycle.md).
- Browse the [Counter example](counter.md) for a smaller starting point.
- See [Reactivity](../concepts/reactivity.md) for `create_memo` and `dynamic` semantics.
