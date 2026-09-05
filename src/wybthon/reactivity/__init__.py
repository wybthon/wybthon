"""Wybthon's reactive system.

Signals, memos, effects, and the scheduler that ties them together. This
package is pure Python and runs anywhere (CPython, Pyodide); nothing here
touches the DOM. Import from `wybthon` in application code; the
submodules are implementation detail.
"""

from ._actions import Action, action, affects, create_optimistic, until
from ._core import (
    Accessor,
    Computation,
    LiteralValue,
    Memo,
    NotReadyError,
    Owner,
    Prop,
    Signal,
    Transition,
    WriteInScopeError,
    flush,
    get_observer,
    get_owner,
    is_accessor,
    literal,
    run_with_owner,
    untrack,
)
from ._list import create_selector, map_array
from ._primitives import (
    Setter,
    children,
    create_effect,
    create_memo,
    create_render_effect,
    create_root,
    create_signal,
    create_tracked_effect,
    create_unique_id,
    is_pending,
    latest,
    on_cleanup,
    on_settled,
    refresh,
    resolve,
)
from ._props import Props, merge, omit, prop

__all__ = [
    # Types
    "Accessor",
    "LiteralValue",
    "literal",
    "Setter",
    "Signal",
    "Memo",
    "Prop",
    "Props",
    "Owner",
    "Computation",
    "Transition",
    "Action",
    # Errors
    "NotReadyError",
    "WriteInScopeError",
    # Primitives
    "create_signal",
    "create_memo",
    "create_effect",
    "create_tracked_effect",
    "create_render_effect",
    "on_settled",
    "on_cleanup",
    "create_root",
    "flush",
    "untrack",
    "get_owner",
    "get_observer",
    "run_with_owner",
    # Async
    "is_pending",
    "latest",
    "refresh",
    "resolve",
    "action",
    "create_optimistic",
    "affects",
    "until",
    # Props
    "prop",
    "merge",
    "omit",
    "children",
    # Lists
    "map_array",
    "create_selector",
    # Misc
    "create_unique_id",
    "is_accessor",
]
