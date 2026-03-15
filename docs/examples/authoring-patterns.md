### Authoring Patterns Example

This example mirrors the demo app's Patterns page and showcases:

- State with `create_signal` and derived values with `create_memo`
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

```python
from wybthon import div, h

def Page(_props):
    return div(
        h(Card, {"title": "State & Derived"}, h(NamesList, {})),
        h(Card, {"title": "Cleanup"}, h(Timer, {})),
    )
```

See the guide for deeper discussion: [Authoring Patterns](../guides/authoring-patterns.md)


