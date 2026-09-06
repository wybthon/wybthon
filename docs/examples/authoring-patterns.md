# Authoring patterns example

A single page that exercises the idioms from the [Authoring patterns guide](../guides/authoring-patterns.md):

- Composition through `children` (a `Card` component that forwards `**rest`).
- State with `create_signal` and derived values with `create_memo`.
- Reactive list rendering with `For` over a draft-first store.
- A mutation wrapped in `action` with a pending indicator.
- Cleanup with `on_settled` and `on_cleanup` (a ticking `Timer`).

!!! warning "Name the helper"
    The `children` prop and the [`children`][wybthon.children] helper collide when a component declares a `children` parameter. Import the helper under another name, as the listing does with `from wybthon import children as resolve_children`.

## Full listing

```python
from wybthon import (
    For,
    Prop,
    Show,
    action,
    button,
    component,
    create_memo,
    create_signal,
    create_store,
    div,
    h3,
    input_,
    li,
    on_cleanup,
    on_settled,
    p,
    prop,
    render,
    section,
    span,
    ul,
)
from wybthon import children as resolve_children


@component
def Card(title: Prop[str] = prop(""), children: Prop = prop(None), **rest):
    kids = resolve_children(children)
    return section(h3(title), kids, class_="card", **rest)


@component
def NamesList():
    store, set_store = create_store({"names": []})
    draft, set_draft = create_signal("")

    total = create_memo(lambda: len(store.names))
    starts_with_a = create_memo(lambda: sum(1 for n in store.names if n["text"].lower().startswith("a")))

    @action
    async def add(text: str):
        # Simulate a slow save; the button is disabled while ``add.pending()``.
        import asyncio

        await asyncio.sleep(0.3)
        set_store(lambda s: s.names.append({"id": len(s.names) + 1, "text": text}))
        set_draft("")

    def clear(e):
        set_store(lambda s: s.names.clear())

    return div(
        p(lambda: f"Total: {total()} | Starts with A: {starts_with_a()}"),
        div(
            input_(value=draft, on_input=lambda e: set_draft(e.target.value), placeholder="Name"),
            button("Add", on_click=lambda e: add(draft.peek()), disabled=add.pending),
            button("Clear", on_click=clear),
        ),
        Show(add.pending, lambda: p("Saving...")),
        ul(
            For(
                lambda: store.names,
                lambda item, index: li(lambda: f"{index() + 1}. {item()['text']}"),
                fallback=li("No names yet."),
                keyed=lambda n: n["id"],
            )
        ),
    )


@component
def Timer():
    seconds, set_seconds = create_signal(0)

    def start():
        from js import clearInterval, setInterval
        from pyodide.ffi import create_proxy

        proxy = create_proxy(lambda: set_seconds(lambda s: s + 1))
        handle = setInterval(proxy, 1000)

        def stop():
            clearInterval(handle)
            proxy.destroy()

        return stop  # cleanup runs on unmount

    on_settled(start)
    on_cleanup(lambda: print("Timer unmounted"))

    return div(span(lambda: f"Seconds: {seconds()}"), class_="timer")


@component
def Page():
    show_timer, set_show_timer = create_signal(True)
    return div(
        Card(NamesList(), title="State and derived values", id="names"),
        Card(
            button("Toggle timer", on_click=lambda e: set_show_timer(lambda v: not v)),
            Show(show_timer, lambda: Timer()),
            title="Cleanup",
        ),
    )


render(Page(), "#app")
```

## What to notice

- `Card` declares the props it handles and forwards everything else with `**rest`. The parent's `id="names"` lands on the `<section>`.
- `NamesList` keeps its list in a store. `set_store(lambda s: s.names.append(...))` mutates a draft; only the leaf signals that changed notify, and `For` matches rows by `id` so existing `<li>` elements are kept.
- With a key function, `For` hands the row callback accessors for both the item and the index, so the row text reads `item()` and `index()` inside a hole.
- `add` is an [`action`][wybthon.action]. While it's in flight, `add.pending()` is `True`, which disables the button and shows the "Saving..." line.
- `Timer` starts its interval in [`on_settled`][wybthon.on_settled] and returns a cleanup from it, so the interval stops when `Show` unmounts the timer. [`on_cleanup`][wybthon.on_cleanup] in the body runs at the same time.

## Next steps

- Read [Components](../concepts/components.md) and [Lifecycle and Ownership](../concepts/lifecycle.md).
- Browse the [Counter example](counter.md) for a smaller starting point.
- See [Stores](../concepts/stores.md) for `reconcile`, `snapshot`, and derived stores.
