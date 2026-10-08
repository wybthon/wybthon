# Authoring patterns example

A single page that exercises the idioms from the [Authoring patterns guide](../guides/authoring-patterns.md):

- Composition through `children` (a `Card` component built on `ParentProps` that forwards an `id` with `omit`).
- State with `create_signal` and derived values with `create_memo`.
- Reactive list rendering with `For` over a draft-first store.
- A mutation wrapped in `action` with a pending indicator.
- Cleanup with `on_settled` and `on_cleanup` (a ticking `Timer`).

## Full listing

```python
from wybthon import (
    For,
    ParentProps,
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
    omit,
    on_cleanup,
    on_settled,
    p,
    prop,
    render,
    section,
    span,
    ul,
)


class CardProps(ParentProps):
    title: Prop[str] = prop(default="")
    id: Prop[str | None] = prop(default=None)


@component
def Card(props: CardProps):
    return section(h3(props.title), props.children, class_="card", **omit(props, "title", "children"))


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

    def clear():
        set_store(lambda s: s.names.clear())

    return div(
        p(t"Total: {total} | Starts with A: {starts_with_a}"),
        div(
            input_(value=draft, on_input=lambda e: set_draft(e.target.value), placeholder="Name"),
            button("Add", on_click=lambda: add(draft.peek()), disabled=add.pending),
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

    return div(span(t"Seconds: {seconds}"), class_="timer")


@component
def Page():
    show_timer, set_show_timer = create_signal(True)
    return div(
        Card(title="State and derived values", id="names")[NamesList()],
        Card(title="Cleanup")[
            button("Toggle timer", on_click=lambda: set_show_timer(lambda v: not v)),
            Show(show_timer, lambda: Timer()),
        ],
    )


render(Page(), "#app")
```

## What to notice

- `Card` subclasses `ParentProps`, so it accepts children, and declares the props it handles. It forwards `id` by spreading `omit(props, "title", "children")` onto the `<section>`, so the parent's `id="names"` lands there. A `None` value removes the attribute.
- `Page` passes each card's children with item syntax: `Card(title=...)[...]`.
- `NamesList` keeps its list in a store. `set_store(lambda s: s.names.append(...))` mutates a draft; only the leaf signals that changed notify, and `For` matches rows by `id` so existing `<li>` elements are kept.
- With a key function, `For` hands the row callback accessors for both the item and the index, so the row text reads `item()` and `index()` inside a hole.
- The summary line is a t-string: `total` and `starts_with_a` are memos, read inside one binding.
- `add` is an [`action`][wybthon.action]. While it's in flight, `add.pending()` is `True`, which disables the button and shows the "Saving..." line.
- Handlers that don't need the event take no arguments (`on_click=clear`); `on_input` takes the event to read `e.target.value`.
- `Timer` starts its interval in [`on_settled`][wybthon.on_settled] and returns a cleanup from it, so the interval stops when `Show` unmounts the timer. [`on_cleanup`][wybthon.on_cleanup] in the body runs at the same time.

## Next steps

- Read [Components](../concepts/components.md) and [Lifecycle and Ownership](../concepts/lifecycle.md).
- Browse the [Counter example](counter.md) for a smaller starting point.
- See [Stores](../concepts/stores.md) for `reconcile`, `snapshot`, and derived stores.
