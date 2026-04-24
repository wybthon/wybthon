### Events

Event handlers are delegated at the document root.

```python
from wybthon import h

def Button(props):
    return h("button", {"on_click": lambda evt: print("clicked")}, "Click")
```

Supported prop names: `on_click`, `on_input`, `on_change`, etc. Both `on_foo` and `onFoo` styles are supported; they normalize to DOM event names.

#### DomEvent

Handlers receive a `DomEvent` object that wraps the browser event and provides a small, Python-friendly surface:

- `type`: the event type string (e.g., `"click"`, `"input"`).
- `target`: an `Element` for the original event target node (or `None`). Common form-input properties (`value`, `checked`, `files`) are exposed directly on the wrapper, mirroring the JS DOM API. The raw JS node is also available via `target.element`.
- `current_target`: an `Element` for the node whose handler is currently running during delegated bubbling. This is set for you before your handler is called.
- `prevent_default()`: calls `preventDefault()` on the underlying JS event, if available. Safe to call in non-browser tests.
- `stop_propagation()`: stops delegated propagation within Wybthon's dispatcher for this event. It also attempts to call the underlying JS `stopPropagation()` when available.

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

Wybthon installs one document-level listener per event type on first use and walks up from the original `target` to parent nodes, invoking any handlers that were registered on matching virtual nodes. `stop_propagation()` prevents further bubbling within Wybthon's dispatcher.

Cleanup guarantees:

- When a node is unmounted, all of its event handlers are removed from the delegation map.
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

When you need non-bubbling events or special options (e.g., `passive: False`), attach directly via `Ref` and `Element.on`:

```python
from wybthon import component, div, on_mount, Ref

@component
def HoverDemo():
    ref = Ref()

    def setup():
        if ref.current is not None:
            ref.current.on("mouseenter", lambda e: print("entered"))

    on_mount(setup)

    return div("Hover me", ref=ref, class_="box")
```

#### Pyodide cross-browser notes

- Delegation depends on bubbling to `document`. For non-bubbling types, use alternatives or `Element.on`.
- Chrome/Edge may treat `touchstart`/`touchmove` on `document` as passive, so `preventDefault()` may be ignored. Use a direct listener with `options={"passive": False}` if you need to prevent scrolling.
- `keypress` is deprecated; prefer `keydown`/`keyup`.

## Next steps

- Read [Forms](forms.md) for higher-level controlled-input patterns.
- See [DOM Interop](dom.md) for the underlying `Element` and `Ref` APIs.
- Browse the [`events`][wybthon.events] API reference for delegation internals.
