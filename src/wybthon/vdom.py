"""Virtual DOM primitives, diffing, and rendering to real DOM elements.

This module re-exports the public API from the focused sub-modules:

- :mod:`wybthon.vnode` -- ``VNode``, ``h``, ``Fragment``, ``memo``
- :mod:`wybthon.reconciler` -- ``render``, ``mount``, ``unmount``, ``patch``
- :mod:`wybthon.error_boundary` -- ``ErrorBoundary``
- :mod:`wybthon.suspense` -- ``Suspense``
- :mod:`wybthon.portal` -- ``create_portal``
- :mod:`wybthon.props` -- prop-diffing helpers (``is_event_prop``, etc.)

All names previously importable from ``wybthon.vdom`` continue to work.
"""

from .error_boundary import ErrorBoundary
from .portal import create_portal
from .props import is_event_prop
from .reconciler import mount, patch, render, unmount
from .suspense import Suspense
from .vnode import Fragment, VNode, h, memo

__all__ = [
    "VNode",
    "h",
    "Fragment",
    "render",
    "ErrorBoundary",
    "Suspense",
    "memo",
    "create_portal",
    "is_event_prop",
    "mount",
    "unmount",
    "patch",
]

_is_event_prop = is_event_prop
_unmount = unmount
