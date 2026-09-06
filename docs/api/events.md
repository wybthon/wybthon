### wybthon.events

::: wybthon.events

#### What's in this module

Event handling is **delegated at the render root**. The JS kernel
installs one native listener per event type on each container passed to
[`render`][wybthon.render] (falling back to `document` when no root is
registered), walks the ancestor chain natively when an event fires, and
calls into Python once for the matching bubbling route with a small JSON payload.
Handlers receive a [`DomEvent`][wybthon.DomEvent] built from that
payload, so the common reads (`evt.target.value`, `evt.key`) never touch
a `JsProxy`. Registering a handler is itself a batched `LISTEN` op.

| Name | Description |
| --- | --- |
| [`DomEvent`][wybthon.DomEvent] | The event object: `type`, `target` (`.value`, `.checked`, `.files`, `.element`), `current_target`, `key`, `code`, `alt_key`, `ctrl_key`, `meta_key`, `shift_key`, `button`, `client_x`, `client_y`, `prevent_default()`, `stop_propagation()`, `raw`. |

`set_handler`, `remove_handlers_for`, and `dispatch_event` are internal
entry points used by the renderer and the kernel.

#### Handler props

- Any prop named `on_<type>` (or `on<Type>`) is a handler: `on_click`,
  `on_input`, `on_keydown`, `onChange`. The prefix is stripped and the
  remainder lower-cased to get the DOM event type.
- Handlers take one argument, the `DomEvent`. Signal writes made inside
  a handler are flushed automatically when it returns, so the DOM
  updates before the browser paints.
- `evt.raw` is the native event and is valid only synchronously during
  dispatch.

```python
from wybthon import DomEvent, create_signal, form, input_, ul, li

items, set_items = create_signal([])
draft, set_draft = create_signal("")

def submit(evt: DomEvent) -> None:
    evt.prevent_default()
    set_items(lambda xs: [*xs, draft.peek()])
    set_draft("")

def keydown(evt: DomEvent) -> None:
    if evt.key == "Escape":
        set_draft("")

view = form(
    input_(value=draft, on_input=lambda e: set_draft(e.target.value), on_keydown=keydown),
    ul(lambda: [li(x) for x in items()]),
    on_submit=submit,
)
```

#### Delegation notes

- Because delegation relies on bubbling, non-bubbling types don't reach
  prop handlers. Use `focusin`/`focusout` instead of `focus`/`blur`, and
  `mouseover`/`mouseout` instead of `mouseenter`/`mouseleave`. For
  `scroll`, media events, or listener options such as `passive`, attach
  a native listener through a [`Ref`][wybthon.Ref] inside
  [`on_settled`][wybthon.on_settled] and remove it in the cleanup it
  returns.
- `stop_propagation()` stops both the delegated walk and native
  propagation; `prevent_default()` is applied by the kernel after the
  handler returns.
- Unmounting a subtree drops its handlers on the Python side, and the
  `RELEASE` op clears the kernel's listener bookkeeping. `Root.dispose()`
  unregisters the container as a delegation root.
- In CPython tests the stub backend exposes `dispatch(event_type, node)`
  to run the handler chain; see the [testing guide](../guides/testing.md).

#### See also

- [Props](props.md): how handler props are recognized
- [Kernel](kernel.md): `LISTEN`, `UNLISTEN`, `ROOT`, and the dispatch payload
- [Concepts: Events](../concepts/events.md)
- [Concepts: Forms](../concepts/forms.md)
