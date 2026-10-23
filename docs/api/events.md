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

- In a template, an attribute named `on<type>` is a handler:
  `onclick={save}`, `oninput={edit}`. `onClick` and `on:click` work
  too. The DOM event type is the rest of the name, lower-cased.
- In a spread (`<input {bind_text(field)}>`) or an [`h()`][wybthon.h]
  props dict, a key named `on_<type>` (or `on<Type>`) is a handler:
  `on_click`, `on_input`, `on_keydown`, `onChange`.
- A capture suffix listens in the capture phase: `onClickCapture` in a
  template, `on_click_capture` in a spread or `h()` props.
- A handler takes the `DomEvent` or no arguments at all; the arity is
  checked once, at registration. Signal writes made inside a handler
  are flushed automatically when it returns, so the DOM updates before
  the browser paints.
- The compiler never wraps a handler: `onclick={save}` passes `save`
  itself, and `onclick={make_handler(id)}` calls `make_handler` once,
  when the template is created. Python doesn't allow a bare `lambda` as
  a whole interpolation, so name the handler, or wrap an inline one in
  parentheses: `onclick={(lambda: set_open(False))}`.
- `evt.raw` is the native event and is valid only synchronously during
  dispatch.

```python
from wybthon import DomEvent, create_signal, event, html

items, set_items = create_signal([])
draft, set_draft = create_signal("")


def submit(evt: DomEvent) -> None:
    evt.prevent_default()
    set_items(lambda xs: [*xs, draft.peek()])
    set_draft("")


def edit(evt: DomEvent) -> None:
    set_draft(evt.target.value)


def keydown(evt: DomEvent) -> None:
    if evt.key == "Escape":
        set_draft("")


def clear() -> None:  # no event needed
    set_items([])


ignore_touch = event(lambda: None, passive=True)  # direct native listener

view = html(t"""
  <form onsubmit={submit} ontouchstart={ignore_touch}>
    <input value={draft()} oninput={edit} onkeydown={keydown}>
    <button type="button" onclick={clear}>Clear</button>
    <ul>{[html(t"<li>{x}</li>") for x in items()]}</ul>
  </form>
""")
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

- [Templates](../concepts/templates.md#interpolations): event attributes in templates
- [VNode: prop names and values](vnode.md#prop-names-and-values): handler names in spreads and `h()` props
- [Kernel](kernel.md): `REGISTER_TPL`, `LISTEN`, `UNLISTEN`, `ROOT`, and the dispatch payload
- [Concepts: Events](../concepts/events.md)
- [Concepts: Forms](../concepts/forms.md)
