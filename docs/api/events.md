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
a `JsProxy`. Registering a handler costs no bridge crossing: handlers
on template-mounted nodes are declared by the template itself, so a
cloned row marks its listeners natively, and other handlers ride the
command buffer as a batched `LISTEN` op.

| Name | Description |
| --- | --- |
| [`DomEvent`][wybthon.DomEvent] | The event object: `type`, `target` (`.value`, `.checked`, `.files`, `.element`), `current_target`, `key`, `code`, `alt_key`, `ctrl_key`, `meta_key`, `shift_key`, `button`, `client_x`, `client_y`, `prevent_default()`, `stop_propagation()`, `raw`. |
| [`event`][wybthon.event] | `event(handler, *, capture=False, passive=False, once=False)`: attach a direct native listener with options instead of delegating. |
| [`EventHandler`][wybthon.EventHandler] | What `event` returns: the callback plus its listener options. |

`set_handler`, `remove_handlers_for`, and `dispatch_event` are internal
entry points used by the renderer and the kernel.

#### Handler props

- Any prop named `on_<type>` (or `on<Type>`) is a handler: `on_click`,
  `on_input`, `on_keydown`, `onChange`. The prefix is stripped and the
  remainder lower-cased to get the DOM event type.
- A handler takes the `DomEvent` or no arguments at all
  (`on_click=lambda: set_open(False)`); the arity is checked once, at
  registration. Signal writes made inside a handler are flushed
  automatically when it returns, so the DOM updates before the browser
  paints.
- `evt.raw` is the native event and is valid only synchronously during
  dispatch.

```python
from wybthon import DomEvent, button, create_signal, event, form, input_, li, ul

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
    button("Clear", type="button", on_click=lambda: set_items([])),  # no event needed
    ul(lambda: [li(x) for x in items()]),
    on_submit=submit,
    on_touchstart=event(lambda: None, passive=True),  # direct native listener
)
```

#### Delegation notes

- Delegation relies on bubbling, so non-bubbling types (`focus`, `blur`,
  `mouseenter`, `mouseleave`, `pointerenter`, `pointerleave`, `scroll`,
  `load`, `error`, `invalid`, and `toggle`) get a direct native listener
  on the element instead. For listener options such as `passive` or
  `capture`, wrap the handler in [`event`][wybthon.event], which also
  attaches a direct listener.
- `stop_propagation()` stops both the delegated walk and native
  propagation; `prevent_default()` is applied by the kernel after the
  handler returns.
- Unmounting a subtree drops its handlers on the Python side, and the
  kernel's `DISPOSE_RANGE` or `DISPOSE` command clears its listener
  bookkeeping natively. `Root.dispose()` unregisters the container as a
  delegation root.
- In CPython tests, [`wybthon.testing`](testing.md) fires events
  through the real dispatcher: `fire.click(node)`,
  `fire.input(node, value)`, `fire.key_down(node, key)`.

#### See also

- [HTML helpers](html.md): how handler props are recognized
- [Kernel](kernel.md): `REGISTER_TPL`, `LISTEN`, `UNLISTEN`, `ROOT`, and the dispatch payload
- [Concepts: Events](../concepts/events.md)
- [Concepts: Forms](../concepts/forms.md)
