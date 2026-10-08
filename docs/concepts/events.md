# Events

Event handlers are `on_*` props on host elements. They're delegated:
one native listener per event type per render root, with a single
Python call per handler that matches.

```python
from wybthon import button, component


@component
def Button():
    return button("Click", on_click=lambda: print("clicked"))
```

Supported prop names: `on_click`, `on_input`, `on_change`, and so on.
Both `on_foo` and `onFoo` styles are accepted and normalize to DOM
event names. Non-callable values are ignored, and passing `None` on an
update removes the handler.

A handler may take the event or no arguments at all. Wybthon checks the
handler's signature once, when it's registered, so a zero-argument
handler costs nothing extra. Prefer one whenever you don't read the
event:

```python
button("+", on_click=lambda: set_count(lambda n: n + 1))
```

## DomEvent

Handlers that take an argument receive a [`DomEvent`][wybthon.DomEvent]
built from a small payload the kernel assembles natively, so reading the
common fields never crosses the Python-to-JS bridge:

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
from wybthon import DomEvent, button, component, form, input_


@component
def Search():
    def submit(evt: DomEvent):
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
from the original target natively and calls into Python once for the
bubbling route, running each handler registered for that type along the
way. The payload crosses the bridge as one JSON string, so a click on a
row in a 10,000-row table costs a single Python call.

Registering a handler costs no bridge crossing of its own. A compiled
template declares its delegated listener types when it's registered, so
cloning a row marks its handlers natively and sends no `LISTEN` op.
Other handlers register with a batched `LISTEN` op riding the same
command buffer as DOM mutations. Either way, mounting a list with
thousands of handlers adds nothing to the bridge-crossing count.

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

- When a node is unmounted, its handlers are dropped on the Python side. The kernel's native `DISPOSE_RANGE` or `DISPOSE` op removes the nodes and clears their listener bookkeeping in the same walk, so Python sends no per-node release list.
- When the last handler for an event type is removed across the whole app (by unmount, or by diffing a handler to `None`), the native listener for that type is removed from every root.

## Naming and normalization

- `on_click` becomes `"click"`.
- `onInput` and `on_input` both become `"input"`.
- `onClick` and `onclick` become `"click"`.
- A `_capture` suffix listens in the capture phase: `on_click_capture`.
- Any prop starting with `on_` or `on` is treated as an event handler.

## Event types that work best with delegation

Prefer events that bubble:

- Mouse: `click`, `dblclick`, `mousedown`, `mouseup`, `mousemove`, `mouseover`, `mouseout`, `contextmenu`, `wheel`
- Keyboard: `keydown`, `keyup` (avoid the deprecated `keypress`)
- Input and form: `input`, `change`, `submit`, `reset`
- Pointer: `pointerdown`, `pointerup`, `pointermove`, `pointerover`, `pointerout`, `pointercancel`

Non-bubbling events still work as props. `focus`, `blur`,
`mouseenter`, `mouseleave`, `pointerenter`, `pointerleave`, `scroll`,
`load`, `error`, `invalid`, and `toggle` get a direct native listener on
their node instead of the delegated one. Use `focusin` and `focusout`
when an ancestor should hear focus changes from its descendants.

## Native listeners through a ref

For anything the props don't cover, such as a third-party library that
wants the element itself, attach a native listener directly through
Pyodide using a [`Ref`][wybthon.Ref]. Refs are assigned during mount, so
do the wiring in [`on_settled`][wybthon.on_settled], which runs after
the first commit. Wrap the handler in `create_proxy` so it survives
garbage collection, and remove it on cleanup:

```python
from pyodide.ffi import create_proxy

from wybthon import Ref, component, div, on_cleanup, on_settled


@component
def DropZone():
    ref = Ref()
    proxy = create_proxy(lambda e: print("files dropped"))

    def setup():
        if ref.current is not None:
            ref.current.element.addEventListener("drop", proxy)

    def teardown():
        if ref.current is not None:
            ref.current.element.removeEventListener("drop", proxy)
        proxy.destroy()

    on_settled(setup)
    on_cleanup(teardown)

    return div("Drop files here", ref=ref, class_="drop-zone")
```

Reading `ref.current.element` commits any pending batched ops first, so
the node exists and reflects every queued mutation. See
[DOM interop](dom.md).

## Pyodide cross-browser notes

- Delegation depends on bubbling to the render root. Non-bubbling types use direct listeners automatically, as described above.
- Chrome and Edge may treat `touchstart` and `touchmove` listeners as passive, so `prevent_default()` may be ignored for them. Use `event(handler, passive=False)` or a direct listener with `{"passive": False}` options if you need to prevent scrolling.
- `keypress` is deprecated; prefer `keydown` and `keyup`.

## Testing handlers

[`wybthon.testing`](../api/testing.md) renders into an in-memory DOM in
plain CPython and dispatches events through the same delegated handlers. Each [`fire`][wybthon.testing.fire] helper flushes when the
handlers return, just as in the browser:

```python
from wybthon import button, component, create_signal, div, p
from wybthon.testing import fire, render


@component
def Counter():
    count, set_count = create_signal(0)
    return div(p(t"Count: {count}"), button("+", on_click=lambda: set_count(lambda n: n + 1)))


def test_counter():
    with render(Counter()) as screen:
        fire.click(screen.get_by_text("+"))
        assert screen.get_by_text("Count: 1")
```

`fire.input(node, value)`, `fire.change(node, checked=True)`,
`fire.submit(form)`, and `fire.key_down(node, "Enter")` set the matching
payload fields. `fire(node, "dblclick", shift_key=True)` dispatches any
other type.

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
