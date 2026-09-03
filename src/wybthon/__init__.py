"""Wybthon: SolidJS for Python, running in the browser on Pyodide.

Wybthon brings SolidJS 2.0's signals-first reactive model to Python.
Component bodies run **once** at mount; reactivity flows through
*reactive holes*: accessors embedded in the VNode tree that update only
the DOM nodes that depend on them. A virtual DOM batches every mutation
into a single crossing of the Python-to-JavaScript bridge.

Highlights of the reactive model:

- **Automatic batching.** Signal writes are staged and applied on the
  next flush (a microtask, and after each event handler). There is no
  `batch()`; everything batches. Call [`flush`][wybthon.flush] to
  settle now.
- **Typed accessors.** [`create_signal`][wybthon.create_signal] returns
  `(Accessor[T], Setter[T])`; call the accessor to read (tracked),
  `.peek()` to read without subscribing.
- **Async-first.** A memo whose body is `async def` (or an async
  generator) is an async computation: [`Loading`][wybthon.Loading]
  boundaries show fallbacks until it resolves, later recomputes serve
  the stale value while revalidating, and
  [`is_pending`][wybthon.is_pending] / [`latest`][wybthon.latest]
  observe in-flight state. [`refresh`][wybthon.refresh] and
  [`resolve`][wybthon.resolve] drive it imperatively.
- **Actions and optimistic state.** [`action`][wybthon.action] tracks
  in-flight mutations; [`create_optimistic`][wybthon.create_optimistic]
  and [`create_optimistic_store`][wybthon.create_optimistic_store]
  hold temporary values that revert when the actions settle.
- **Draft-first stores.** [`create_store`][wybthon.create_store]
  setters take a function that mutates a draft with plain Python.
- **Dev diagnostics.** Writes inside a tracking scope raise
  [`WriteInScopeError`][wybthon.WriteInScopeError]; reading a signal
  at the top level of a component body warns.

Everything is importable outside a browser (CPython), so unit tests
and tooling run anywhere; the DOM is only touched when rendering.

Example:
    A minimal counter component:

    ```python
    from wybthon import Prop, button, component, create_signal, div, p, prop, render

    @component
    def Counter(initial: Prop[int] = prop(0)):
        count, set_count = create_signal(initial.peek())
        return div(
            p("Count: ", count),
            button("+1", on_click=lambda e: set_count(lambda n: n + 1)),
        )

    render(Counter(initial=5), "#app")
    ```

See Also:
    * [Getting started](https://wybthon.com/getting-started/)
    * [Mental model](https://wybthon.com/concepts/mental-model/)
    * [API reference](https://wybthon.com/api/wybthon/)
"""

from ._warnings import DEV_MODE, is_dev_mode, set_dev_mode
from .component import Component, component
from .context import Context, ContextNotFoundError, create_context, use_context
from .dom import Element, Ref
from .error_boundary import Errored
from .events import DomEvent
from .flow import Dynamic, For, Match, Repeat, Show, Switch
from .forms import (
    Field,
    Validator,
    a11y_control_attrs,
    bind_checkbox,
    bind_select,
    bind_text,
    email,
    error_message_attrs,
    form_state,
    max_length,
    min_length,
    on_submit,
    on_submit_validated,
    required,
    rules_from_schema,
    validate,
    validate_field,
    validate_form,
)
from .html import (
    a,
    article,
    aside,
    audio,
    blockquote,
    br,
    button,
    canvas,
    caption,
    code,
    col,
    colgroup,
    details,
    dialog,
    div,
    element,
    em,
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
    hr,
    img,
    input_,
    label,
    legend,
    li,
    main_,
    mark,
    meter,
    nav,
    ol,
    optgroup,
    option,
    p,
    picture,
    pre,
    progress,
    section,
    select,
    small,
    source,
    span,
    strong,
    summary,
    table,
    tbody,
    td,
    textarea,
    tfoot,
    th,
    thead,
    time,
    tr,
    track,
    ul,
    video,
)
from .lazy import lazy
from .loading import Loading, Reveal
from .portal import Portal
from .reactivity import (
    Accessor,
    Action,
    Computation,
    Memo,
    NotReadyError,
    Owner,
    Prop,
    Props,
    Setter,
    Signal,
    WriteInScopeError,
    action,
    children,
    create_effect,
    create_memo,
    create_optimistic,
    create_render_effect,
    create_root,
    create_selector,
    create_signal,
    create_unique_id,
    flush,
    get_observer,
    get_owner,
    is_accessor,
    is_pending,
    latest,
    map_array,
    merge,
    omit,
    on_cleanup,
    on_settled,
    prop,
    refresh,
    resolve,
    run_with_owner,
    untrack,
)
from .reconciler import Root, render
from .router import Link, Route, Router, current_path, navigate, use_base_path, use_params, use_query
from .store import (
    create_optimistic_store,
    create_projection,
    create_store,
    deep,
    reconcile,
    snapshot,
    store_path,
)
from .vnode import Fragment, VNode, h, hole

__version__ = "0.31.0"

__all__ = [
    # Components
    "component",
    "Component",
    "Prop",
    "Props",
    "prop",
    "merge",
    "omit",
    "children",
    # VDOM
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
    "Computation",
    "Owner",
    "create_signal",
    "create_memo",
    "create_effect",
    "create_render_effect",
    "create_root",
    "create_unique_id",
    "flush",
    "on_settled",
    "on_cleanup",
    "untrack",
    "get_owner",
    "get_observer",
    "run_with_owner",
    "map_array",
    "create_selector",
    "WriteInScopeError",
    # Async
    "NotReadyError",
    "is_pending",
    "latest",
    "refresh",
    "resolve",
    "action",
    "Action",
    "create_optimistic",
    # Context
    "Context",
    "ContextNotFoundError",
    "create_context",
    "use_context",
    # Flow control
    "Show",
    "For",
    "Repeat",
    "Switch",
    "Match",
    "Dynamic",
    # Boundaries
    "Loading",
    "Reveal",
    "Errored",
    "Portal",
    "lazy",
    # Stores
    "create_store",
    "create_projection",
    "create_optimistic_store",
    "reconcile",
    "store_path",
    "snapshot",
    "deep",
    # Forms
    "Field",
    "Validator",
    "form_state",
    "bind_text",
    "bind_checkbox",
    "bind_select",
    "validate",
    "validate_field",
    "validate_form",
    "required",
    "min_length",
    "max_length",
    "email",
    "on_submit",
    "on_submit_validated",
    "rules_from_schema",
    "a11y_control_attrs",
    "error_message_attrs",
    # DOM
    "Element",
    "Ref",
    "render",
    "Root",
    "DomEvent",
    # Router
    "Router",
    "Route",
    "Link",
    "navigate",
    "current_path",
    "use_params",
    "use_query",
    "use_base_path",
    # Dev mode
    "DEV_MODE",
    "set_dev_mode",
    "is_dev_mode",
    # HTML element helpers
    "div",
    "span",
    "p",
    "a",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "ul",
    "ol",
    "li",
    "button",
    "form",
    "input_",
    "label",
    "select",
    "option",
    "optgroup",
    "textarea",
    "table",
    "thead",
    "tbody",
    "tfoot",
    "tr",
    "th",
    "td",
    "caption",
    "colgroup",
    "col",
    "progress",
    "meter",
    "img",
    "br",
    "hr",
    "mark",
    "time",
    "section",
    "article",
    "nav",
    "header",
    "footer",
    "main_",
    "strong",
    "em",
    "small",
    "code",
    "pre",
    "blockquote",
    "fieldset",
    "legend",
    "video",
    "audio",
    "source",
    "canvas",
    "picture",
    "track",
    "details",
    "summary",
    "dialog",
    "figure",
    "figcaption",
    "aside",
]
