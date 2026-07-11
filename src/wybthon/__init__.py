"""Wybthon: a client-side Python SPA framework powered by Pyodide.

Wybthon brings a SolidJS-inspired, signals-first reactive model to the
browser using Python. Component bodies run **once** at mount; reactivity
flows through *reactive holes*: zero-arg getters embedded in the VNode
tree that update only the DOM nodes that depend on them.

The package detects its environment at import time:

- In a browser (Pyodide), the full surface is available, including DOM
  helpers, reconciler, router, events, error boundaries, suspense,
  portals, and the HTML element factories.
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
    ReactiveProps,
    Resource,
    Signal,
    batch,
    catch_error,
    children,
    create_computed,
    create_deferred,
    create_effect,
    create_memo,
    create_reaction,
    create_render_effect,
    create_resource,
    create_root,
    create_selector,
    create_signal,
    create_unique_id,
    get_owner,
    get_props,
    index_array,
    map_array,
    merge_props,
    on,
    on_cleanup,
    on_error,
    on_mount,
    run_with_owner,
    split_props,
    untrack,
)
from .store import create_mutable, create_store, modify_mutable, produce, reconcile, unwrap

# Pure-Python VDOM data structures are available in any environment.
from .vnode import Fragment, VNode, dynamic, h, is_getter

__version__ = "0.27.0"

_IN_BROWSER = False
try:
    importlib.import_module("js")
    _IN_BROWSER = True
except Exception:
    _IN_BROWSER = False

if _IN_BROWSER:
    from .context import Context, Provider, create_context, use_context
    from .dom import Element, Ref
    from .error_boundary import ErrorBoundary
    from .events import DomEvent
    from .flow import Dynamic, For, Index, Match, Show, Switch
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
        nav,
        ol,
        option,
        p,
        pre,
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
        th,
        thead,
        tr,
        ul,
        video,
    )
    from .lazy import lazy
    from .portal import Portal
    from .reconciler import render
    from .router import Link, Route, Router, current_path, navigate
    from .suspense import Suspense, SuspenseList

    __all__ = [
        # DOM
        "Element",
        "Ref",
        # Components
        "component",
        "forward_ref",
        # VDOM
        "VNode",
        "h",
        "Fragment",
        "render",
        "ErrorBoundary",
        "Suspense",
        "SuspenseList",
        "Portal",
        "dynamic",
        "is_getter",
        # Reactivity
        "create_signal",
        "create_effect",
        "create_render_effect",
        "create_computed",
        "create_deferred",
        "create_memo",
        "create_reaction",
        "create_resource",
        "create_root",
        "create_unique_id",
        "catch_error",
        "batch",
        "on_mount",
        "on_cleanup",
        "on_error",
        "untrack",
        "on",
        "get_props",
        "merge_props",
        "split_props",
        "map_array",
        "index_array",
        "create_selector",
        "Resource",
        "ReactiveProps",
        "Signal",
        "Computed",
        "get_owner",
        "run_with_owner",
        "children",
        # Events
        "DomEvent",
        # Context
        "Context",
        "create_context",
        "use_context",
        "Provider",
        # Router
        "Router",
        "Route",
        "Link",
        "navigate",
        "current_path",
        # Flow control
        "Show",
        "For",
        "Index",
        "Switch",
        "Match",
        "Dynamic",
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
        # Stores
        "create_store",
        "create_mutable",
        "modify_mutable",
        "produce",
        "reconcile",
        "unwrap",
        # Lazy loading
        "lazy",
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
        "textarea",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
        "caption",
        "img",
        "br",
        "hr",
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
        "details",
        "summary",
        "dialog",
        "figure",
        "figcaption",
        "aside",
    ]
else:
    from .context import Context, Provider, create_context, use_context
    from .flow import Dynamic, For, Index, Match, Show, Switch

    __all__ = [
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
        "create_computed",
        "create_deferred",
        "create_memo",
        "create_reaction",
        "create_resource",
        "create_root",
        "create_unique_id",
        "catch_error",
        "batch",
        "on_mount",
        "on_cleanup",
        "on_error",
        "untrack",
        "on",
        "get_props",
        "merge_props",
        "split_props",
        "map_array",
        "index_array",
        "create_selector",
        "Resource",
        "ReactiveProps",
        "Signal",
        "Computed",
        "get_owner",
        "run_with_owner",
        "children",
        # Context
        "Context",
        "create_context",
        "use_context",
        "Provider",
        # Flow control
        "Show",
        "For",
        "Index",
        "Switch",
        "Match",
        "Dynamic",
        # Stores
        "create_store",
        "create_mutable",
        "modify_mutable",
        "produce",
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
        "DEV_MODE",
        "set_dev_mode",
        "is_dev_mode",
    ]
