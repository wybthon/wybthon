"""Top-level Wybthon package API and browser/runtime detection.

This module exposes the public surface area for both browser (Pyodide) and
non-browser environments, importing DOM/VDOM features only when available.
"""

import importlib

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
from .hooks import HookRef, use_callback, use_effect, use_memo, use_ref, use_state
from .reactivity import Resource, batch, computed, effect, on_effect_cleanup, signal, use_resource

__version__ = "0.10.0"

# Detect Pyodide/browser environment where `js` module exists
_IN_BROWSER = False
try:
    importlib.import_module("js")
    _IN_BROWSER = True
except Exception:
    _IN_BROWSER = False

if _IN_BROWSER:
    # Import browser/VDOM-related modules only when running under Pyodide
    from .component import Component
    from .context import Context, Provider, create_context, use_context
    from .dom import Element, Ref
    from .events import DomEvent
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
    from .router import Link, Route, Router, current_path, navigate
    from .vdom import ErrorBoundary, Fragment, Suspense, VNode, h, render

    __all__ = [
        # DOM
        "Element",
        "Ref",
        # Components
        "Component",
        # VDOM
        "VNode",
        "h",
        "Fragment",
        "render",
        "ErrorBoundary",
        "Suspense",
        # Reactivity
        "signal",
        "computed",
        "effect",
        "batch",
        "on_effect_cleanup",
        "use_resource",
        "Resource",
        # Hooks
        "use_state",
        "use_effect",
        "use_memo",
        "use_ref",
        "use_callback",
        "HookRef",
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
        # Lazy loading
        "lazy",
        "load_component",
        "preload_component",
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
    # Minimal Python-only surface for tooling/CLI usage (no browser modules)
    __all__ = [
        "signal",
        "computed",
        "effect",
        "batch",
        "on_effect_cleanup",
        "use_resource",
        "Resource",
        "use_state",
        "use_effect",
        "use_memo",
        "use_ref",
        "use_callback",
        "HookRef",
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
    ]
