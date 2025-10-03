### wybthon.events

Wybthon’s event system provides delegated event handling and a thin `DomEvent` wrapper.

- `DomEvent`: wrapper with `type`, `target` (`Element|None`), `current_target` (`Element|None`), `prevent_default()`, `stop_propagation()`.
- Handlers can be attached via props like `on_click`, `on_input`, or `onChange`. Names are normalized to DOM event types.
- Delegation is automatic and handlers are cleaned up on unmount.

::: wybthon.events
