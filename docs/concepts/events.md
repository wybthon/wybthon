### Events

Event handlers are delegated at the document root.

```python
from wybthon import h

def Button(props):
    return h("button", {"on_click": lambda evt: print("clicked")}, "Click")
```

Supported prop names: `on_click`, `on_input`, `on_change`, etc. Both `on_foo` and `onFoo` styles are supported; they normalize to DOM event names.

#### DomEvent

Handlers receive a `DomEvent` object built from a small payload the
dispatcher assembles natively, so reading it never crosses the
Python-to-JS bridge:

- `type`: the event type string (e.g., `"click"`, `"input"`).
- `target`: a payload-backed view of the original event target. The properties handlers actually read (`value`, `checked`, `files`) are exposed directly, mirroring the JS DOM API. The raw JS node is available via `target.element` as an escape hatch.
- `current_target`: an `Element` for the node whose handler is currently running during delegated bubbling. This is set for you before your handler is called.
- `key`, `code`, `alt_key`, `ctrl_key`, `meta_key`, `shift_key`, `button`, `client_x`, `client_y`: keyboard and mouse fields, straight from the payload.
- `prevent_default()`: marks the event so the dispatcher calls `preventDefault()` on the native event. Safe to call in non-browser tests.
- `stop_propagation()`: stops delegated propagation for this event, including native propagation above the handled node.
- `raw`: the native browser event object, for anything not covered by the payload. Only valid synchronously during dispatch.

Read input values exactly like in JS/React/SolidJS:

```python
input_(
    value=name,
    on_input=lambda e: set_name(e.target.value),
)
```

Example:

```python
from wybthon import h

def Form(props):
    def on_submit(evt):
        evt.prevent_default()
        print("submitted from", evt.current_target)

    return h("form", {"on_submit": on_submit},
             h("input", {"name": "q", "on_input": lambda e: print("input", e.target)}),
             h("button", {"type": "submit"}, "Go"))
```

#### Delegation model

Delegation lives in the rendering kernel (the JavaScript side of the
batched renderer). The kernel installs one document-level listener per
event type on first use, walks up from the original `target` natively,
and calls into Python once per node that actually registered a handler
for that type. The payload crosses the bridge as one JSON string, so a
click on a row in a 10,000-row table costs a single Python call.

Registering a handler is itself a batched op (`LISTEN`), riding the
same command buffer as the DOM mutations; mounting a list with
thousands of handlers adds nothing to the bridge-crossing count.

Cleanup guarantees:

- When a node is unmounted, its handlers are dropped on the Python side and the kernel's listener bookkeeping is cleared by the same `RELEASE` op that retires the node ids.
- When the last handler for an event type is removed across the entire document (e.g., via unmount or by diffing a handler to `None`), the document-level listener for that event type is automatically removed.

#### Naming and normalization

- `on_click` becomes "click"
- `onInput`/`on_input` becomes "input"
- `onClick`/`onclick` becomes "click"
- Any prop starting with `on_` or `on` is treated as an event handler; non-callable values are ignored.

#### Event types that work best with delegation

Prefer events that bubble:

- Mouse: `click`, `dblclick`, `mousedown`, `mouseup`, `mousemove`, `mouseover`, `mouseout`, `contextmenu`, `wheel`
- Keyboard: `keydown`, `keyup` (avoid deprecated `keypress`)
- Input and form: `input`, `change`, `submit`, `reset`
- Pointer: `pointerdown`, `pointerup`, `pointermove`, `pointerover`, `pointerout`, `pointercancel`

Non-bubbling alternatives:

- Use `focusin`/`focusout` instead of `focus`/`blur`.
- Use `mouseover`/`mouseout` instead of `mouseenter`/`mouseleave`.

When you need non-bubbling events or special options (e.g., `passive: False`), attach a native listener directly through Pyodide using a `Ref`. Wrap the handler in `create_proxy` so it survives garbage collection, and remove it on cleanup:

```python
from pyodide.ffi import create_proxy

from wybthon import Ref, component, div, on_cleanup, on_mount

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

    on_mount(setup)
    on_cleanup(teardown)

    return div("Hover me", ref=ref, class_="box")
```

#### Pyodide cross-browser notes

- Delegation depends on bubbling to `document`. For non-bubbling types, use the alternatives above or a direct `addEventListener` via `Ref`.
- Chrome/Edge may treat `touchstart`/`touchmove` on `document` as passive, so `preventDefault()` may be ignored. Use a direct listener with `{"passive": False}` options if you need to prevent scrolling.
- `keypress` is deprecated; prefer `keydown`/`keyup`.

## Next steps

- Read [Forms](forms.md) for higher-level controlled-input patterns.
- See [DOM Interop](dom.md) for the underlying `Element` and `Ref` APIs.
- Browse the [`events`][wybthon.events] API reference for delegation internals.
