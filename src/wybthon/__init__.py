"""Wybthon: SolidJS for Python, running in the browser on Pyodide.

Wybthon brings SolidJS 2.0's signals-first reactive model to Python.
Component bodies run **once** at mount and return markup written as a
t-string template, [`html(t"...")`][wybthon.html], which compiles once
per literal into a native template the kernel clones. Reactivity flows
through *reactive holes*: accessors placed in the markup that update
only the DOM nodes that depend on them. A virtual DOM batches every
mutation into a single crossing of the Python-to-JavaScript bridge.

Highlights of the reactive model:

- **Automatic batching.** Signal writes are staged and applied on the
  next flush (a microtask, and after each event handler). There is no
  `batch()`; everything batches. Call [`flush`][wybthon.flush] to
  settle now.
- **Typed accessors.** [`create_signal`][wybthon.create_signal] returns
  `(Accessor[T], Setter[T])`; call the accessor to read (tracked),
  `.peek()` to read without subscribing.
- **Typed props.** Components declare inputs on a
  [`Props`][wybthon.Props] class; pyright and mypy check every call
  without a plugin.
- **Async-first, with transitions.** A memo whose body is `async def`
  (or an async generator) is an async computation:
  [`Loading`][wybthon.Loading] boundaries show fallbacks until it first
  resolves. A later recompute opens a **transition**: the UI that
  depends on the changed input holds its previous, consistent state
  until the new value lands, so a new id never shows next to old data.
  [`is_pending`][wybthon.is_pending] / [`latest`][wybthon.latest]
  observe the in-flight state; [`refresh`][wybthon.refresh] and
  [`resolve`][wybthon.resolve] drive it imperatively.
- **Actions are transactions.** [`action`][wybthon.action] holds a
  transition open while a mutation runs, so its writes land together;
  [`create_optimistic`][wybthon.create_optimistic] and
  [`create_optimistic_store`][wybthon.create_optimistic_store] show
  temporary values immediately and revert when it settles;
  [`affects`][wybthon.affects] and [`until`][wybthon.until] describe
  what the action changes and wait for it to land.
- **Draft-first stores.** [`create_store`][wybthon.create_store]
  setters take a function that mutates a draft with plain Python.
- **Server rendering.** [`wybthon.server`][wybthon.server] renders
  the same components to HTML in CPython, including async data and
  out-of-order streaming; [`hydrate`][wybthon.hydrate] adopts that HTML
  in the browser instead of rebuilding it.
- **Dev diagnostics.** Writes inside a tracking scope raise
  [`WriteInScopeError`][wybthon.WriteInScopeError]; reading a signal
  at the top level of a component body warns.

Everything is importable outside a browser (CPython), so unit tests
and tooling run anywhere; the DOM is only touched when rendering.

Example:
    A minimal counter component:

    ```python
    from wybthon import Prop, Props, component, create_signal, html, prop, render


    class CounterProps(Props):
        initial: Prop[int] = prop(default=0)


    @component
    def Counter(props: CounterProps):
        count, set_count = create_signal(props.initial.peek())

        def increment():
            set_count(lambda n: n + 1)

        return html(t"<div><p>Count: {count}</p><button onclick={increment}>+1</button></div>")


    render(Counter(initial=5), "#app")
    ```

See Also:
    * [Getting started](https://wybthon.com/getting-started/)
    * [Mental model](https://wybthon.com/concepts/mental-model/)
    * [Templates](https://wybthon.com/concepts/templates/)
    * [API reference](https://wybthon.com/api/wybthon/)
"""

from typing import TYPE_CHECKING, Any

from ._warnings import is_dev_mode, set_dev_mode
from .component import Component, component
from .context import Context, ContextNotFoundError, create_context, use_context
from .dom import Element, Ref
from .elements import (
    a,
    abbr,
    address,
    area,
    article,
    aside,
    audio,
    b,
    bdi,
    bdo,
    blockquote,
    br,
    button,
    canvas,
    caption,
    cite,
    code,
    col,
    colgroup,
    data,
    datalist,
    dd,
    del_,
    details,
    dfn,
    dialog,
    div,
    dl,
    dt,
    element,
    em,
    embed,
    fieldset,
    figcaption,
    figure,
    footer,
    form,
    h1,
    h2,
    h3,
    h4,
    h5,
    h6,
    header,
    hgroup,
    hr,
    i,
    iframe,
    img,
    input_,
    ins,
    kbd,
    label,
    legend,
    li,
    main_,
    map_,
    mark,
    menu,
    meter,
    nav,
    object_,
    ol,
    optgroup,
    option,
    output,
    p,
    picture,
    pre,
    progress,
    q,
    rp,
    rt,
    ruby,
    s,
    samp,
    search,
    section,
    select,
    slot,
    small,
    source,
    span,
    strong,
    sub,
    summary,
    sup,
    table,
    tbody,
    td,
    template,
    textarea,
    tfoot,
    th,
    thead,
    time,
    tr,
    track,
    u,
    ul,
    var,
    video,
    wbr,
)
from .error_boundary import Errored
from .events import DomEvent, EventHandler, event
from .flow import For, Hydration, Match, NoHydration, Repeat, Show, Switch, client_only, dynamic, is_hydrating
from .lazy import lazy
from .loading import Loading, Reveal
from .portal import Portal
from .reactivity import (
    Accessor,
    Action,
    ChildrenAccessor,
    Memo,
    NotReadyError,
    Owner,
    ParentProps,
    Prop,
    Props,
    ServerError,
    Setter,
    Signal,
    WriteInScopeError,
    action,
    affects,
    children,
    create_effect,
    create_memo,
    create_optimistic,
    create_owner,
    create_reaction,
    create_render_effect,
    create_root,
    create_signal,
    create_tracked_effect,
    create_unique_id,
    flush,
    get_observer,
    get_owner,
    is_accessor,
    is_disposed,
    is_pending,
    is_server,
    latest,
    map_array,
    merge,
    omit,
    on_cleanup,
    on_settled,
    prop,
    refresh,
    repeat,
    resolve,
    run_with_owner,
    until,
    untrack,
)
from .reconciler import Root, hydrate, render
from .request import RequestEvent, ResponseHead, get_request_event, http_header, http_status
from .templates import TemplateError, html
from .vnode import Fragment, VNode, h, hole

if TYPE_CHECKING:
    from .store import (
        Draft,
        DraftExpiredError,
        DraftList,
        Store,
        StoreList,
        StoreSetter,
        create_optimistic_store,
        create_projection,
        create_store,
        deep,
        reconcile,
        snapshot,
    )

# Stores load on first use: they're a sizable part of startup and many
# pages never use them.
_LAZY = {
    name: ".store"
    for name in (
        "Draft",
        "DraftExpiredError",
        "DraftList",
        "Store",
        "StoreList",
        "StoreSetter",
        "create_optimistic_store",
        "create_projection",
        "create_store",
        "deep",
        "reconcile",
        "snapshot",
    )
}


def __getattr__(name: str) -> Any:
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module 'wybthon' has no attribute {name!r}")
    from importlib import import_module

    value = getattr(import_module(module, __name__), name)
    globals()[name] = value
    return value


__version__ = "0.37.0"

__all__ = [
    # Components and props
    "component",
    "Component",
    "Props",
    "ParentProps",
    "Prop",
    "prop",
    "merge",
    "omit",
    "children",
    "ChildrenAccessor",
    # Templates and nodes
    "html",
    "TemplateError",
    "VNode",
    "h",
    "hole",
    "Fragment",
    "element",
    "is_accessor",
    # Reactivity
    "Accessor",
    "Setter",
    "Signal",
    "Memo",
    "Owner",
    "create_signal",
    "create_memo",
    "create_effect",
    "create_tracked_effect",
    "create_render_effect",
    "create_reaction",
    "create_root",
    "create_owner",
    "is_disposed",
    "create_unique_id",
    "flush",
    "on_settled",
    "on_cleanup",
    "untrack",
    "get_owner",
    "get_observer",
    "run_with_owner",
    "map_array",
    "repeat",
    "WriteInScopeError",
    # Async
    "NotReadyError",
    "ServerError",
    "is_pending",
    "latest",
    "refresh",
    "resolve",
    "action",
    "Action",
    "create_optimistic",
    "affects",
    "until",
    # Stores
    "Store",
    "StoreList",
    "StoreSetter",
    "Draft",
    "DraftList",
    "DraftExpiredError",
    "create_store",
    "create_optimistic_store",
    "create_projection",
    "reconcile",
    "snapshot",
    "deep",
    # Flow control
    "Show",
    "For",
    "Repeat",
    "Switch",
    "Match",
    "dynamic",
    "client_only",
    # Boundaries
    "Loading",
    "Reveal",
    "Errored",
    # Context
    "Context",
    "ContextNotFoundError",
    "create_context",
    "use_context",
    # Portal and code splitting
    "Portal",
    "lazy",
    # DOM
    "Element",
    "Ref",
    "DomEvent",
    "EventHandler",
    "event",
    # Rendering
    "render",
    "hydrate",
    "Root",
    "is_server",
    "is_hydrating",
    "NoHydration",
    "Hydration",
    "RequestEvent",
    "ResponseHead",
    "get_request_event",
    "http_status",
    "http_header",
    # Dev mode
    "is_dev_mode",
    "set_dev_mode",
    # HTML elements
    "a",
    "abbr",
    "address",
    "area",
    "article",
    "aside",
    "audio",
    "b",
    "bdi",
    "bdo",
    "blockquote",
    "br",
    "button",
    "canvas",
    "caption",
    "cite",
    "code",
    "col",
    "colgroup",
    "data",
    "datalist",
    "dd",
    "del_",
    "details",
    "dfn",
    "dialog",
    "div",
    "dl",
    "dt",
    "em",
    "embed",
    "fieldset",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hgroup",
    "hr",
    "i",
    "iframe",
    "img",
    "input_",
    "ins",
    "kbd",
    "label",
    "legend",
    "li",
    "main_",
    "map_",
    "mark",
    "menu",
    "meter",
    "nav",
    "object_",
    "ol",
    "optgroup",
    "option",
    "output",
    "p",
    "picture",
    "pre",
    "progress",
    "q",
    "rp",
    "rt",
    "ruby",
    "s",
    "samp",
    "search",
    "section",
    "select",
    "slot",
    "small",
    "source",
    "span",
    "strong",
    "sub",
    "summary",
    "sup",
    "table",
    "tbody",
    "td",
    "template",
    "textarea",
    "tfoot",
    "th",
    "thead",
    "time",
    "tr",
    "track",
    "u",
    "ul",
    "var",
    "video",
    "wbr",
]
