"""Virtual DOM primitives, diffing, and rendering to real DOM elements.

This module is a thin compatibility shim that re-exports the public API
from the focused sub-modules. Existing code that imports from
`wybthon.vdom` continues to work unchanged.

Re-exports:

- [`wybthon.vnode`][wybthon.vnode]: `VNode`, `h`, `Fragment`, `memo`,
  `dynamic`, `is_getter`.
- [`wybthon.reconciler`][wybthon.reconciler]: `render`, `mount`,
  `unmount`, `patch`.
- [`wybthon.error_boundary`][wybthon.error_boundary]: `ErrorBoundary`.
- [`wybthon.suspense`][wybthon.suspense]: `Suspense`.
- [`wybthon.portal`][wybthon.portal]: `create_portal`.
- [`wybthon.props`][wybthon.props]: prop-diffing helpers
  (`is_event_prop`, etc.).
"""

from .error_boundary import ErrorBoundary
from .portal import create_portal
from .props import is_event_prop
from .reconciler import mount, patch, render, unmount
from .suspense import Suspense
from .vnode import Fragment, VNode, dynamic, h, is_getter, memo

__all__ = [
    "VNode",
    "h",
    "Fragment",
    "render",
    "ErrorBoundary",
    "Suspense",
    "memo",
    "create_portal",
    "dynamic",
    "is_getter",
    "is_event_prop",
    "mount",
    "unmount",
    "patch",
]

_is_event_prop = is_event_prop
_unmount = unmount
