### wybthon.events

::: wybthon.events

Wybthon’s event system provides delegated event handling and a thin `DomEvent` wrapper.

- `DomEvent`: wrapper with `type`, `target` (`Element|None`), `current_target` (`Element|None`), `prevent_default()`, `stop_propagation()`.
- Handlers can be attached via props like `on_click`, `on_input`, or `onChange`. Names are normalized to DOM event types.
- Delegation is automatic and handlers are cleaned up on unmount. Document-level delegated listeners are installed on first use per event type and are automatically removed when no handlers remain for that type (e.g., after unmount/diff removes all handlers).

#### Naming and normalization

- Any prop starting with `on_` or `on` is treated as an event handler and normalized to a DOM event type.
- Normalization rules:
  - `on_click` → "click"
  - `onInput`/`on_input` → "input"
  - `onClick`/`onclick` → "click"
  - In general: remove the `on`/`on_` prefix and lowercase the remainder.

Handler signature:

- All handlers receive a `DomEvent` object. Use `evt.prevent_default()` and `evt.stop_propagation()` as needed. Access the original JS event via `evt._js_event` only if absolutely necessary.

#### Delegation and bubbling

Wybthon installs one document-level listener per event type on first use and walks up from the original `target` to parent nodes, invoking any handlers registered for that `event_type`. `stop_propagation()` prevents further bubbling within Wybthon’s dispatcher.

Cleanup guarantees:

- When a node is unmounted, all of its event handlers are removed from the delegation map.
- When the last handler for an event type is removed across the entire document (e.g., via unmount or by diffing a handler to `None`), the document-level listener for that event type is automatically removed.

#### Common event types

You can attach handlers for any standard DOM event that bubbles. Commonly used types include:

- Mouse: `click`, `dblclick`, `mousedown`, `mouseup`, `mousemove`, `mouseover`, `mouseout`, `contextmenu`, `wheel`
- Keyboard: `keydown`, `keyup` (avoid deprecated `keypress`)
- Input and form: `input`, `change`, `submit`, `reset`
- Focus: use `focusin` and `focusout` (see non-bubbling notes below)
- Pointer: `pointerdown`, `pointerup`, `pointermove`, `pointerover`, `pointerout`, `pointercancel`
- Touch: `touchstart`, `touchmove`, `touchend`, `touchcancel`
- Composition/IME: `compositionstart`, `compositionupdate`, `compositionend`
- Drag and drop: `dragstart`, `dragend`, `dragenter`, `dragleave`, `dragover`, `drop`

Wybthon does not restrict event type names; if the browser fires it and it bubbles, the delegated listener will see it.

#### Non-bubbling and special-case events

Because Wybthon uses document-level delegation, event types that do not bubble will not trigger handlers when attached via props. Use the suggested alternatives or attach a direct listener via `wybthon.dom.Element.on` using a `Ref`.

- Use `focusin`/`focusout` instead of `focus`/`blur` (which do not bubble).
- Use `mouseover`/`mouseout` instead of `mouseenter`/`mouseleave` (which do not bubble).
- Many media events (e.g., `play`, `pause`) and `scroll` do not bubble; attach direct listeners to the element or use `window`/`document` as appropriate.

Direct listeners example (when you need non-bubbling events or options like `passive`: False):

```python
from wybthon import Component, h, Ref

class Video(Component):
    def __init__(self, props):
        super().__init__(props)
        self.ref = Ref()

    def on_mount(self):
        if self.ref.current is not None:
            self.ref.current.on("play", lambda e: print("playing"))

    def render(self):
        return h("video", {"ref": self.ref})
```

#### Pyodide and cross-browser notes

- Event delegation relies on bubbling to `document`. For non-bubbling types, prefer the alternatives above or attach direct listeners via `Element.on`.
- Chrome/Edge may treat `touchstart`/`touchmove` listeners on `document` as passive by default, making `preventDefault()` a no-op. If you need to prevent scrolling, attach a direct listener with `options={"passive": False}` using `Element.on` and a `Ref`.
- `keypress` is deprecated and may behave inconsistently across browsers; prefer `keydown`/`keyup`.
- The `DomEvent` wrapper exposes a stable, Python-friendly surface. Accessing `evt._js_event` is possible but not recommended for portability across Pyodide and non-browser tests.
