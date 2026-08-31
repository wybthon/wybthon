"""Wybthon: a client-side Python SPA framework powered by Pyodide.

Wybthon brings a SolidJS-inspired, signals-first reactive model to the
browser using Python, matching the semantics of SolidJS 2.0. Component
bodies run **once** at mount; reactivity flows through *reactive
holes*: zero-arg getters embedded in the VNode tree that update only
the DOM nodes that depend on them.

Highlights of the reactive model:

- **Automatic batching.** Signal writes apply immediately, and every
  dependent effect runs on the next flush (a browser microtask, and
  after each event handler). There is no `batch()`; everything batches.
- **Async-first.** A memo whose body is `async def` is an async
  computation: [`Loading`][wybthon.Loading] boundaries show fallbacks
  until it resolves, later recomputes serve the stale value while
  revalidating, and [`is_pending`][wybthon.is_pending] /
  [`latest`][wybthon.latest] observe in-flight state.
- **Actions and optimistic state.** [`action`][wybthon.action] tracks
  in-flight mutations; [`create_optimistic`][wybthon.create_optimistic]
  and [`create_optimistic_store`][wybthon.create_optimistic_store]
  hold temporary values that revert when the actions settle.
- **Draft-first stores.** [`create_store`][wybthon.create_store]
  setters take a function that mutates a draft with plain Python.

The package detects its environment at import time:

- In a browser (Pyodide), the full surface is available, including DOM
  helpers, reconciler, router, events, error boundaries, loading
  boundaries, portals, and the HTML element factories.
- Outside a browser, the pure-Python surface (reactivity, VDOM data
  structures, forms, context, flow control, stores) remains importable
  so unit tests and tooling can run anywhere CPython runs.

Example:
    A minimal counter component::

        from wybthon import button, component, create_signal, div, p, span

        @component
        def Counter(initial: int = 0):
            count, set_count = create_signal(initial)
            return div(
                p("Count: ", span(count)),
                button("+1", on_click=lambda e: set_count(count() + 1)),
            )

See Also:
    * [Getting started](https://wybthon.com/getting-started/)
    * [Mental model](https://wybthon.com/concepts/mental-model/)
    * [API reference](https://wybthon.com/api/wybthon/)
"""

import importlib

from ._warnings import DEV_MODE, is_dev_mode, set_dev_mode
from .component import component, forward_ref
from .forms import (
    FieldState,
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
from .reactivity import (
    Computed,
    NotReadyError,
    ReactiveProps,
    Signal,
    action,
    catch_error,
    children,
    create_effect,
    create_memo,
    create_optimistic,
    create_reaction,
    create_render_effect,
    create_root,
    create_selector,
    create_signal,
    create_unique_id,
    flush,
    get_owner,
    get_props,
    index_array,
    is_pending,
    latest,
    map_array,
    merge_props,
    on_cleanup,
    on_error,
    on_mount,
    run_with_owner,
    split_props,
    untrack,
)
from .store import create_optimistic_store, create_projection, create_store, reconcile, unwrap

# Pure-Python VDOM data structures are available in any environment.
from .vnode import Fragment, VNode, dynamic, h, is_getter

__version__ = "0.28.0"

_IN_BROWSER = False
try:
    importlib.import_module("js")
    _IN_BROWSER = True
except Exception:
    _IN_BROWSER = False

# Names shared by the browser and pure-Python surfaces; the browser
# branch below extends this list with its extra exports.
__all__ = [
    # Components
    "component",
    "forward_ref",
    # VDOM (pure-Python; usable for tree construction without a browser)
    "VNode",
    "h",
    "Fragment",
    "dynamic",
    "is_getter",
    # Reactivity
    "create_signal",
    "create_effect",
    "create_render_effect",
    "create_memo",
    "create_reaction",
    "create_root",
    "create_unique_id",
    "catch_error",
    "flush",
    "on_mount",
    "on_cleanup",
    "on_error",
    "untrack",
    "get_props",
    "merge_props",
    "split_props",
    "map_array",
    "index_array",
    "create_selector",
    "ReactiveProps",
    "Signal",
    "Computed",
    "get_owner",
    "run_with_owner",
    "children",
    # Async
    "NotReadyError",
    "is_pending",
    "latest",
    "action",
    "create_optimistic",
    # Context
    "Context",
    "create_context",
    "use_context",
    "Provider",
    # Flow control
    "Show",
    "For",
    "Repeat",
    "Switch",
    "Match",
    "Dynamic",
    # Stores
    "create_store",
    "create_projection",
    "create_optimistic_store",
    "reconcile",
    "unwrap",
    # Forms
    "bind_text",
    "bind_checkbox",
    "bind_select",
    "form_state",
    "FieldState",
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
    # Dev mode
    "DEV_MODE",
    "set_dev_mode",
    "is_dev_mode",
]

if _IN_BROWSER:
    from .context import Context, Provider, create_context, use_context
    from .dom import Element, Ref
    from .error_boundary import ErrorBoundary
    from .events import DomEvent
    from .flow import Dynamic, For, Match, Repeat, Show, Switch
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
    from .loading import Loading, LoadingList
    from .portal import Portal
    from .reconciler import render
    from .router import Link, Route, Router, current_path, navigate

    __all__ += [
        # DOM
        "Element",
        "Ref",
        "render",
        "ErrorBoundary",
        "Loading",
        "LoadingList",
        "Portal",
        # Events
        "DomEvent",
        # Router
        "Router",
        "Route",
        "Link",
        "navigate",
        "current_path",
        # Lazy loading
        "lazy",
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
else:
    from .context import Context, Provider, create_context, use_context
    from .flow import Dynamic, For, Match, Repeat, Show, Switch
