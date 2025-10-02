import importlib

from .forms import (
    bind_checkbox,
    bind_select,
    bind_text,
    email,
    form_state,
    max_length,
    min_length,
    on_submit,
    required,
    validate,
)
from .reactivity import batch, computed, effect, on_effect_cleanup, signal, use_resource

__version__ = "0.1.0"

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
    from .router import Link, Route, Router, current_path, navigate
    from .vdom import ErrorBoundary, VNode, h, render

    __all__ = [
        "Element",
        "Ref",
        "BaseComponent",
        "Component",
        "VNode",
        "h",
        "render",
        "ErrorBoundary",
        "signal",
        "computed",
        "effect",
        "batch",
        "on_effect_cleanup",
        "use_resource",
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
        "validate",
        "required",
        "min_length",
        "max_length",
        "email",
        "on_submit",
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
        "bind_text",
        "bind_checkbox",
        "bind_select",
        "form_state",
        "validate",
        "required",
        "min_length",
        "max_length",
        "email",
        "on_submit",
    ]
