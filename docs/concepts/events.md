# Events

Event handlers are `on_*` props on host elements. They're delegated:
one native listener per event type per render root, with a single
Python call per handler that matches.

```python
from wybthon import component
from wybthon.html import button


@component
def Button():
    return button("Click", on_click=lambda evt: print("clicked"))
```

Supported prop names: `on_click`, `on_input`, `on_change`, and so on.
Both `on_foo` and `onFoo` styles are accepted and normalize to DOM
event names. Non-callable values are ignored, and passing `None` on an
update removes the handler.

## DomEvent

Handlers receive a [`DomEvent`][wybthon.DomEvent] built from a small
payload the kernel assembles natively, so reading the common fields
never crosses the Python-to-JS bridge:

- `type`: the event type string (`"click"`, `"input"`).
- `target`: a payload-backed view of the original event target. `value`, `checked`, and `files` mirror the DOM properties handlers actually read; the raw JS node is available as `target.element` when you need more.
- `current_target`: an [`Element`][wybthon.Element] for the node whose handler is running during delegated bubbling.
- `key`, `code`, `alt_key`, `ctrl_key`, `meta_key`, `shift_key`: keyboard fields (`key` and `code` are `None` for non-keyboard events).
- `button`, `client_x`, `client_y`: mouse and pointer fields.
- `prevent_default()`: asks the dispatcher to call `preventDefault()` on the native event once your handler returns. Safe to call in non-browser tests.
- `stop_propagation()`: stops the delegated walk for this event and native propagation above the handled node.
- `raw`: the native browser event object for anything not in the payload. Only valid synchronously during dispatch.

Read input values as you would in JavaScript or SolidJS:

```python
input_(value=name, on_input=lambda e: set_name(e.target.value))
```

A submit handler:

```python
from wybthon import component
from wybthon.html import button, form, input_


@component
def Search():
    def submit(evt):
        evt.prevent_default()
        print("submitted from", evt.current_target)

    return form(
        input_(name="q", on_input=lambda e: print("typed", e.target.value)),
        button("Go", type="submit"),
        on_submit=submit,
    )
```

## Delegation model

Delegation lives in the rendering kernel, the JavaScript side of the
batched renderer. On first use of an event type, the kernel installs one
native listener on each delegation root (the container you passed to
[`render`][wybthon.render] and the mount target of any mounted
[`Portal`][wybthon.Portal]; `document` is used until a root exists).
When an event fires, the kernel walks up
from the original target natively and calls into Python once per node
that registered a handler for that type. The payload crosses the bridge
as one JSON string, so a click on a row in a 10,000-row table costs a
single Python call.

Registering a handler is itself a batched op (`LISTEN`) riding the same
command buffer as DOM mutations; mounting a list with thousands of
handlers adds nothing to the bridge-crossing count.

!!! note "Handlers flush when they return"
    After a delegated handler returns, the dispatcher flushes: every
    effect the handler dirtied runs, and the resulting DOM ops commit in
    one bridge crossing before the browser paints. Signal writes inside
    a handler update the UI without any manual step, no matter how many
    writes the handler made. See
    [Staged writes and flush timing](reactivity.md#staged-writes-and-flush-timing).

Handler errors are logged through the dev-mode error channel; they
aren't routed to an [`Errored`][wybthon.Errored] boundary. See
[Error boundaries](error-boundaries.md#event-handlers-are-not-routed).

Cleanup guarantees:

- When a node is unmounted, its handlers are dropped on the Python side and the kernel's listener bookkeeping is cleared by the same `RELEASE` op that retires the node ids.
- When the last handler for an event type is removed across the whole app (by unmount, or by diffing a handler to `None`), the native listener for that type is removed from every root.

## Naming and normalization

- `on_click` becomes `"click"`.
- `onInput` and `on_input` both become `"input"`.
- `onClick` and `onclick` become `"click"`.
- Any prop starting with `on_` or `on` is treated as an event handler.

## Event types that work best with delegation

Prefer events that bubble:

- Mouse: `click`, `dblclick`, `mousedown`, `mouseup`, `mousemove`, `mouseover`, `mouseout`, `contextmenu`, `wheel`
- Keyboard: `keydown`, `keyup` (avoid the deprecated `keypress`)
- Input and form: `input`, `change`, `submit`, `reset`
- Pointer: `pointerdown`, `pointerup`, `pointermove`, `pointerover`, `pointerout`, `pointercancel`

Non-bubbling alternatives:

- Use `focusin` and `focusout` instead of `focus` and `blur`.
- Use `mouseover` and `mouseout` instead of `mouseenter` and `mouseleave`.

## Native listeners through a ref

When you need a non-bubbling event or listener options (for example
`passive: False`), attach a native listener directly through Pyodide
using a [`Ref`][wybthon.Ref]. Refs are assigned during mount, so do the
wiring in [`on_settled`][wybthon.on_settled], which runs after the first
commit. Wrap the handler in `create_proxy` so it survives garbage
collection, and remove it on cleanup:

```python
from pyodide.ffi import create_proxy

from wybthon import Ref, component, on_cleanup, on_settled
from wybthon.html import div


@component
def HoverDemo():
    ref = Ref()
    proxy = create_proxy(lambda e: print("entered"))

    def setup():
        if ref.current is not None:
            ref.current.element.addEventListener("mouseenter", proxy)

    def teardown():
        if ref.current is not None:
            ref.current.element.removeEventListener("mouseenter", proxy)
        proxy.destroy()

    on_settled(setup)
    on_cleanup(teardown)

    return div("Hover me", ref=ref, class_="box")
```

Reading `ref.current.element` commits any pending batched ops first, so
the node exists and reflects every queued mutation. See
[DOM interop](dom.md).

## Pyodide cross-browser notes

- Delegation depends on bubbling to the render root. For non-bubbling types, use the alternatives above or a direct `addEventListener` via `Ref`.
- Chrome and Edge may treat `touchstart` and `touchmove` listeners as passive, so `prevent_default()` may be ignored for them. Use a direct listener with `{"passive": False}` options if you need to prevent scrolling.
- `keypress` is deprecated; prefer `keydown` and `keyup`.

## Testing handlers

In unit tests, the in-memory kernel backend dispatches events directly:
`kernel._backend.dispatch("click", node, payload={...})`. The payload
keys mirror the browser fields (`value`, `checked`, `key`, `metaKey`,
`button`), and `flush()` runs automatically when the handler returns,
just as in the browser.

## Next steps

- Read [Forms](forms.md) for higher-level controlled-input patterns.
- See [DOM interop](dom.md) for the underlying `Element` and `Ref` APIs.
- Browse the [`events`](../api/events.md) API reference for delegation internals.

## Async handlers and native options

An ordinary `async def` handler is scheduled automatically. It runs in an owned asyncio task and is canceled on handler replacement or unmount. Payload fields and `current_target` remain usable after an await; `event.raw` is valid only during synchronous dispatch. Call `prevent_default` before the first await when you need to prevent native behavior.

```python
from wybthon import button, event

button("Once", on_click=event(save, once=True))
```

`event(callback, capture=True, passive=False, once=False)` configures native listener options. Focus, blur, and other non-bubbling events work through direct listeners. Ordinary bubbling uses `composedPath`, sends one route across the bridge, and flushes after its handlers. Custom event `detail`, composition state, selected option values, and scroll position are included in the payload. A passive handler can't prevent the default action.
