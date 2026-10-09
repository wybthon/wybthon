# Authoring patterns example

A single page that exercises the idioms from the [Authoring patterns guide](../guides/authoring-patterns.md):

- Markup written as [`html`][wybthon.html] templates, with components used as tags.
- Composition through `children` (a `Card` component built on `ParentProps` that forwards an `id` with `omit`).
- State with `create_signal` and derived values with `create_memo`.
- Reactive list rendering with `For` over a draft-first store.
- A mutation wrapped in `action` with a pending indicator.
- Cleanup with `on_settled` and `on_cleanup` (a ticking `Timer`).

## Full listing

```python
import asyncio

from wybthon import (
    For,
    ParentProps,
    Prop,
    Show,
    action,
    component,
    create_memo,
    create_signal,
    create_store,
    html,
    omit,
    on_cleanup,
    on_settled,
    prop,
    render,
)


class CardProps(ParentProps):
    title: Prop[str] = prop(default="")
    id: Prop[str | None] = prop(default=None)


@component
def Card(props: CardProps):
    return html(t"""
      <section class="card" {omit(props, "title", "children")}>
        <h3>{props.title}</h3>
        {props.children}
      </section>
    """)


@component
def NamesList():
    store, set_store = create_store({"names": []})
    draft, set_draft = create_signal("")

    total = create_memo(lambda: len(store.names))
    starts_with_a = create_memo(lambda: sum(1 for n in store.names if n["text"].lower().startswith("a")))

    @action
    async def add(text: str):
        # Simulate a slow save; the button is disabled while ``add.pending()``.
        await asyncio.sleep(0.3)
        set_store(lambda s: s.names.append({"id": len(s.names) + 1, "text": text}))
        set_draft("")

    def save():
        add(draft.peek())

    def clear():
        set_store(lambda s: s.names.clear())

    def edit(e):
        set_draft(e.target.value)

    def row(item, index):
        def label():
            return f"{index() + 1}. {item()['text']}"

        return html(t"<li>{label}</li>")

    return html(t"""
      <div>
        <p>Total: {total} | Starts with A: {starts_with_a}</p>
        <div>
          <input value={draft} oninput={edit} placeholder="Name">
          <button onclick={save} disabled={add.pending}>Add</button>
          <button onclick={clear}>Clear</button>
        </div>
        {Show(add.pending, html(t"<p>Saving...</p>"))}
        <ul>
          {For(store.names, row, fallback=html(t"<li>No names yet.</li>"), keyed=lambda n: n["id"])}
        </ul>
      </div>
    """)


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

    return html(t'<div class="timer"><span>Seconds: {seconds}</span></div>')


@component
def Page():
    show_timer, set_show_timer = create_signal(True)

    def toggle_timer():
        set_show_timer(lambda v: not v)

    return html(t"""
      <div>
        <{Card} title="State and derived values" id="names">
          <{NamesList} />
        </{Card}>
        <{Card} title="Cleanup">
          <button onclick={toggle_timer}>Toggle timer</button>
          {Show(show_timer, Timer())}
        </{Card}>
      </div>
    """)


render(Page(), "#app")
```

## What to notice

- `Card` subclasses `ParentProps`, so it accepts children, and declares the props it handles. It forwards `id` by spreading `omit(props, "title", "children")` onto the `<section>` (`<section {...}>` is a spread), so the parent's `id="names"` lands there. A `None` value removes the attribute.
- `Page` uses the component tag form: `<{Card} title="...">...</{Card}>` passes the attributes as props and the nested markup as `children`, and `<{NamesList} />` takes none. The call form, `{Card(title="Cleanup", children=[...])}` or `Card(title=...)[...]`, does the same and is fully type-checked; dev mode checks the tag form's props at run time.
- `NamesList` keeps its list in a store. `set_store(lambda s: s.names.append(...))` mutates a draft; only the leaf signals that changed notify, and `For` matches rows by `id` so existing `<li>` elements are kept.
- The store list goes to `For` as is: `For(store.names, ...)` tracks it without a wrapping lambda.
- With a key function, `For` hands the row callback accessors for both the item and the index, so `row` reads `item()` and `index()` inside `label`, a function the template turns into a hole.
- The summary line interpolates two memos, `total` and `starts_with_a`; each is its own text binding.
- `add` is an [`action`][wybthon.action]. While it's in flight, `add.pending()` is `True`, which disables the button (`disabled={add.pending}`) and shows the "Saving..." line.
- Handlers that don't need the event take no arguments (`onclick={clear}`); `edit` takes the event to read `e.target.value`. Every handler is a named function, since Python doesn't allow a bare `lambda` inside a t-string interpolation.
- `Show` and `For` mount as native regions, not wrapper components: each is one computation that selects what to render, with no component scope or props of its own.
- `Timer` starts its interval in [`on_settled`][wybthon.on_settled] and returns a cleanup from it, so the interval stops when `Show` unmounts the timer. [`on_cleanup`][wybthon.on_cleanup] in the body runs at the same time. Showing it again mounts a fresh `Timer` with its own state.

## Next steps

- Read [Components](../concepts/components.md) and [Lifecycle and Ownership](../concepts/lifecycle.md).
- Browse the [Counter example](counter.md) for a smaller starting point.
- See [Stores](../concepts/stores.md) for `reconcile`, `snapshot`, and derived stores.
