"""Top-level Wybthon package API and browser/runtime detection.

This module exposes the public surface area for both browser (Pyodide) and
non-browser environments, importing DOM/VDOM features only when available.
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
    Resource,
    batch,
    create_effect,
    create_memo,
    create_resource,
    create_root,
    create_signal,
    merge_props,
    on,
    on_cleanup,
    on_mount,
    split_props,
    untrack,
)
from .store import create_store, produce

__version__ = "0.16.0"

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
    from .lazy import lazy, load_component, preload_component
    from .portal import create_portal
    from .reconciler import render
    from .router import Link, Route, Router, current_path, navigate
    from .suspense import Suspense
    from .vnode import Fragment, VNode, h, memo

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
        "memo",
        "create_portal",
        # Reactivity
        "create_signal",
        "create_effect",
        "create_memo",
        "create_resource",
        "create_root",
        "batch",
        "on_mount",
        "on_cleanup",
        "untrack",
        "on",
        "merge_props",
        "split_props",
        "Resource",
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
        "produce",
        # Lazy loading
        "lazy",
        "load_component",
        "preload_component",
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
        # Reactivity
        "create_signal",
        "create_effect",
        "create_memo",
        "create_resource",
        "create_root",
        "batch",
        "on_mount",
        "on_cleanup",
        "untrack",
        "on",
        "merge_props",
        "split_props",
        "Resource",
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
        "produce",
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
