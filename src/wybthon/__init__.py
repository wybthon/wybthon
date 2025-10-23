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
from .reactivity import Resource, batch, computed, effect, on_effect_cleanup, signal, use_resource

__version__ = "0.8.0"

# Detect Pyodide/browser environment where `js` module exists
_IN_BROWSER = False
try:
    importlib.import_module("js")
    _IN_BROWSER = True
except Exception:
    _IN_BROWSER = False

if _IN_BROWSER:
    # Import browser/VDOM-related modules only when running under Pyodide
    from .component import BaseComponent, Component
    from .context import Context, Provider, create_context, use_context
    from .dom import Element, Ref
    from .events import DomEvent
    from .lazy import lazy, load_component, preload_component
    from .router import Link, Route, Router, current_path, navigate
    from .vdom import ErrorBoundary, Suspense, VNode, h, render

    __all__ = [
        "Element",
        "Ref",
        "BaseComponent",
        "Component",
        "VNode",
        "h",
        "render",
        "ErrorBoundary",
        "Suspense",
        "signal",
        "computed",
        "effect",
        "batch",
        "on_effect_cleanup",
        "use_resource",
        "Resource",
        "DomEvent",
        "Context",
        "create_context",
        "use_context",
        "Provider",
        "Router",
        "Route",
        "Link",
        "navigate",
        "current_path",
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
        "lazy",
        "load_component",
        "preload_component",
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
        "lazy",
        "load_component",
        "preload_component",
    ]
