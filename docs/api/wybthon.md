### wybthon (package)

::: wybthon

#### Public API by area

Everything below is importable with `from wybthon import ...`. Module
pages linked in the left column carry the details.

| Area | Names |
| --- | --- |
| [Templates](templates.md) | `html`, `TemplateError`, `Node` |
| [Components](component.md) | `component`, `Component`, `Children`, `prop`, `merge`, `omit`, `is_static`, `resolve_children`, `flatten`, `ChildrenAccessor` |
| [Reactivity](reactivity.md) | `Accessor`, `Setter`, `Signal`, `Memo`, `create_signal`, `create_memo`, `create_deferred`, `create_effect`, `create_tracked_effect`, `create_render_effect`, `create_root`, `is_disposed`, `is_equal`, `create_unique_id`, `flush`, `on_settled`, `on_flush`, `on_cleanup`, `untrack`, `get_owner`, `run_with_owner`, `WriteInScopeError` |
| [Async](reactivity.md) | `NotReadyError`, `ServerError`, `is_pending`, `latest`, `refresh`, `resolve`, `from_source`, `action`, `Action`, `affects`, `until`, `create_optimistic` |
| [Stores](store.md) | `Store`, `StoreList`, `StoreObject`, `StoreSetter`, `DraftExpiredError`, `create_store`, `create_projection`, `create_optimistic_store`, `reconcile`, `snapshot`, `deep` |
| [Flow control](flow.md) | `Show`, `For`, `Repeat`, `Switch`, `Match`, `dynamic`, `client_only` |
| Boundaries | [`Loading`, `Reveal`](loading.md), [`Errored`](error_boundary.md), [`Portal`](portal.md), [`lazy`, `lazy_module`, `LazyModule`](lazy.md) |
| [Context](context.md) | `Context`, `ContextNotFoundError`, `create_context`, `use_context` |
| DOM and events | [`Element`, `Ref`](dom.md), [`DomEvent`, `EventHandler`, `event`](events.md) |
| Rendering | [`render`, `hydrate`, `Root`](reconciler.md), `is_server`, [`is_hydrating`, `on_hydration_end`, `NoHydration`, `Hydration`](flow.md) |
| [Server requests](request.md) | `RequestEvent`, `ResponseHead`, `get_request_event`, `http_status`, `http_header`, `set_cookie` |
| [Server functions](../concepts/full-stack.md) | `server_function`, `ServerFunction`, `redirect`, `reload`, `respond`, `FormData`, `UploadedFile` |
| Dev mode | `is_dev_mode`, `set_dev_mode`, `WybthonWarning` |

Other modules are imported by name and aren't re-exported:

| Module | Contents |
| --- | --- |
| [`wybthon.router`](router.md) | `create_router`, `Router`, `Route`, `PreloadArgs`, `Outlet`, `navigate`, `url`, `use_location`, `Location`, `use_params`, `Params`, `use_search_params`, `SearchParamsView`, `SearchParams`, `use_route_matches`, `use_link_state`, `LinkState`, `preload_route`, `file_routes`, `match_route`, `RouteSpec`; the data layer: `query`, `revalidate`, `form_action`, `use_submissions` |
| [`wybthon.asgi`](../concepts/full-stack.md) | `create_app`, which serves pages, server functions, and form actions per request |
| [`wybthon.forms`](forms.md) | `form_state`, `FormState`, `Field`, the `bind_*` helpers, validators, and ARIA helpers |
| [`wybthon.server`](server.md) | `render_to_string`, `render_to_stream`, `RenderStream` |
| [`wybthon.testing`](testing.md) | `render`, `Screen`, `fire`, `cleanup`, `raise_unhandled`, and the in-memory DOM |
| [`wybthon.compiler`](compiler.md) | The template compiler: `install`, `uninstall`, `compile_source`, `transform` |
| [`wybthon.virtual`, `wybthon.scheduling`](app-tools.md) | Virtual lists and cooperative scheduling |
| [`wybthon.vnode`](vnode.md) | The node layer for markup built by code: `h`, `hole`, `VNode`, `Fragment` |
| [`wybthon.reactivity`](reactivity.md) | The reactive core, async, and props names above, plus `Owner`, `get_observer`, `create_reaction`, `map_array`, `repeat`, `is_accessor`, `Computation`, and `Transition` |

```python
from wybthon import component, create_signal, html, render, untrack


@component
def Counter(initial: int = 0):
    count, set_count = create_signal(untrack(lambda: initial))

    def increment():
        set_count(lambda n: n + 1)

    return html(t"<div><p>Count: {count()}</p><button onclick={increment}>+1</button></div>")


root = render(Counter(initial=5), "#app")
# later: root.dispose()
```

!!! note "Browser versus CPython"
    Reactivity (including async memos, actions, and `flush`), stores,
    forms, context, flow control, and VDOM construction (`VNode`, `h`,
    `Fragment`, templates) all run in plain CPython, which is how
    the unit tests work. Touching a real DOM (`render` into a page,
    `Element` queries, `navigate` with history) needs Pyodide, or the
    in-memory DOM of [`wybthon.testing`](testing.md).

#### See also

- [Getting started](../getting-started.md)
- [Concepts: Mental model](../concepts/mental-model.md)
- [Guides: Typing](../guides/typing.md)
