### wybthon (package)

::: wybthon

#### Public API by area

Everything below is importable with `from wybthon import ...`. Module
pages linked in the left column carry the details.

| Area | Names |
| --- | --- |
| [Components](component.md) | `component`, `Component`, `Prop`, `Props`, `prop`, `merge`, `omit`, `children` |
| [VDOM](vnode.md) | `VNode`, `h`, `hole`, `Fragment`, `element`, `is_accessor` |
| [Reactivity](reactivity.md) | `Accessor`, `Setter`, `Signal`, `Memo`, `Computation`, `Owner`, `create_signal`, `create_memo`, `create_effect`, `create_render_effect`, `create_root`, `create_unique_id`, `flush`, `on_settled`, `on_cleanup`, `untrack`, `get_owner`, `get_observer`, `run_with_owner`, `map_array`, `create_selector`, `WriteInScopeError` |
| [Async](reactivity.md) | `NotReadyError`, `is_pending`, `latest`, `refresh`, `resolve`, `action`, `Action`, `create_optimistic` |
| [Context](context.md) | `Context`, `ContextNotFoundError`, `create_context`, `use_context` |
| [Flow control](flow.md) | `Show`, `For`, `Repeat`, `Switch`, `Match`, `Dynamic` |
| Boundaries | [`Loading`, `Reveal`](loading.md), [`Errored`](error_boundary.md), [`Portal`](portal.md), [`lazy`](lazy.md) |
| [Stores](store.md) | `create_store`, `create_projection`, `create_optimistic_store`, `reconcile`, `store_path`, `snapshot`, `deep` |
| [Forms](forms.md) | `Field`, `Validator`, `form_state`, `bind_text`, `bind_checkbox`, `bind_select`, `validate`, `validate_field`, `validate_form`, `required`, `min_length`, `max_length`, `email`, `on_submit`, `on_submit_validated`, `rules_from_schema`, `a11y_control_attrs`, `error_message_attrs` |
| DOM and rendering | [`Element`, `Ref`](dom.md), [`render`, `Root`](reconciler.md), [`DomEvent`](events.md) |
| [Router](router.md) | `Router`, `Route`, `Link`, `navigate`, `current_path`, `use_params`, `use_query`, `use_base_path` |
| Dev mode | `DEV_MODE`, `set_dev_mode`, `is_dev_mode` |
| [HTML helpers](html.md) | `div`, `span`, `p`, `a`, `h1` to `h6`, `ul`, `ol`, `li`, `button`, `form`, `input_`, `label`, `select`, `option`, `optgroup`, `textarea`, `table`, `thead`, `tbody`, `tfoot`, `tr`, `th`, `td`, `caption`, `colgroup`, `col`, `progress`, `meter`, `img`, `br`, `hr`, `mark`, `time`, `section`, `article`, `nav`, `header`, `footer`, `main_`, `strong`, `em`, `small`, `code`, `pre`, `blockquote`, `fieldset`, `legend`, `video`, `audio`, `source`, `canvas`, `picture`, `track`, `details`, `summary`, `dialog`, `figure`, `figcaption`, `aside` |

SVG helpers aren't re-exported at the top level; import them from
[`wybthon.svg`](svg.md).

```python
from wybthon import Prop, button, component, create_signal, div, p, prop, render

@component
def Counter(initial: Prop[int] = prop(0)):
    count, set_count = create_signal(initial.peek())
    return div(
        p("Count: ", count),
        button("+1", on_click=lambda e: set_count(lambda n: n + 1)),
    )

root = render(Counter(initial=5), "#app")
# later: root.dispose()
```

!!! note "Browser versus CPython"
    Reactivity (including async memos, actions, and `flush`), stores,
    forms, context, flow control, and VDOM construction (`VNode`, `h`,
    `Fragment`, the HTML helpers) all run in plain CPython, which is how
    the unit tests work. Touching a real DOM (`render` into a page,
    `Element` queries, `navigate` with history) needs Pyodide, or the
    stub backend described in the [testing guide](../guides/testing.md).

#### See also

- [Getting started](../getting-started.md)
- [Concepts: Mental model](../concepts/mental-model.md)
- [Guides: Typing](../guides/typing.md)
