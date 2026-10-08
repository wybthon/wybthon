### wybthon (package)

::: wybthon

#### Public API by area

Everything below is importable with `from wybthon import ...`. Module
pages linked in the left column carry the details.

| Area | Names |
| --- | --- |
| [Components](component.md) | `component`, `Component`, `Props`, `ParentProps`, `Prop`, `prop`, `merge`, `omit`, `children`, `ChildrenAccessor` |
| [VDOM](vnode.md) | `VNode`, `h`, `hole`, `Fragment`, `element`, `is_accessor` |
| [Reactivity](reactivity.md) | `Accessor`, `Setter`, `Signal`, `Memo`, `Owner`, `create_signal`, `create_memo`, `create_effect`, `create_tracked_effect`, `create_render_effect`, `create_reaction`, `create_root`, `create_owner`, `is_disposed`, `create_unique_id`, `flush`, `on_settled`, `on_cleanup`, `untrack`, `get_owner`, `get_observer`, `run_with_owner`, `map_array`, `repeat`, `WriteInScopeError` |
| [Async](reactivity.md) | `NotReadyError`, `ServerError`, `is_pending`, `latest`, `refresh`, `resolve`, `action`, `Action`, `affects`, `until`, `create_optimistic` |
| [Stores](store.md) | `Store`, `StoreList`, `StoreSetter`, `Draft`, `DraftList`, `DraftExpiredError`, `create_store`, `create_projection`, `create_optimistic_store`, `reconcile`, `snapshot`, `deep` |
| [Flow control](flow.md) | `Show`, `For`, `Repeat`, `Switch`, `Match`, `dynamic`, `client_only` |
| Boundaries | [`Loading`, `Reveal`](loading.md), [`Errored`](error_boundary.md), [`Portal`](portal.md), [`lazy`](lazy.md) |
| [Context](context.md) | `Context`, `ContextNotFoundError`, `create_context`, `use_context` |
| DOM and events | [`Element`, `Ref`](dom.md), [`DomEvent`, `EventHandler`, `event`](events.md) |
| Rendering | [`render`, `hydrate`, `Root`](reconciler.md), `is_server`, [`is_hydrating`, `NoHydration`, `Hydration`](flow.md) |
| [Server requests](request.md) | `RequestEvent`, `ResponseHead`, `get_request_event`, `http_status`, `http_header` |
| Dev mode | `is_dev_mode`, `set_dev_mode` |
| [HTML helpers](html.md) | One helper per HTML element (`div`, `p`, `button`, `input_`, ...), plus `element` |

Other modules are imported by name and aren't re-exported:

| Module | Contents |
| --- | --- |
| [`wybthon.router`](router.md) | `Router`, `Route`, `RouteProps`, `Outlet`, `Link`, `navigate`, `current_path`, `use_params`, `use_query`, `use_hash`, `use_base_path`, `preload`, `QueryParams`, `resolve`, `RouteSpec` |
| [`wybthon.forms`](forms.md) | `form_state`, `FormState`, `Field`, the `bind_*` helpers, validators, and ARIA helpers |
| [`wybthon.server`](server.md) | `render_to_string`, `render_to_stream`, `RenderStream` |
| [`wybthon.testing`](testing.md) | `render`, `Screen`, `fire`, `cleanup`, and the in-memory DOM |
| [`wybthon.svg`](svg.md) | SVG element helpers |
| [`wybthon.virtual`, `wybthon.scheduling`](app-tools.md) | Virtual lists and cooperative scheduling |
| [`wybthon.reactivity`](reactivity.md) | Everything above plus `Computation` and `Transition` |

```python
from wybthon import Prop, Props, button, component, create_signal, div, p, prop, render


class CounterProps(Props):
    initial: Prop[int] = prop(default=0)


@component
def Counter(props: CounterProps):
    count, set_count = create_signal(props.initial.peek())
    return div(
        p(t"Count: {count}"),
        button("+1", on_click=lambda: set_count(lambda n: n + 1)),
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
    in-memory DOM of [`wybthon.testing`](testing.md).

#### See also

- [Getting started](../getting-started.md)
- [Concepts: Mental model](../concepts/mental-model.md)
- [Guides: Typing](../guides/typing.md)
