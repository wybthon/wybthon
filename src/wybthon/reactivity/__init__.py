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
    Memo,
    NotReadyError,
    Owner,
    Signal,
    Transition,
    WriteInScopeError,
    flush,
    get_observer,
    get_owner,
    is_accessor,
    run_with_owner,
    untrack,
)
from ._list import map_array, repeat
from ._primitives import (
    ChildrenAccessor,
    Setter,
    children,
    create_effect,
    create_memo,
    create_owner,
    create_reaction,
    create_render_effect,
    create_root,
    create_signal,
    create_tracked_effect,
    create_unique_id,
    is_disposed,
    is_pending,
    is_server,
    latest,
    on_cleanup,
    on_settled,
    refresh,
    resolve,
)
from ._props import ParentProps, Prop, Props, merge, omit, prop
from ._session import ServerError

__all__ = [
    # Types
    "Accessor",
    "Setter",
    "Signal",
    "Memo",
    "Prop",
    "Props",
    "ParentProps",
    "Owner",
    "Computation",
    "Transition",
    "Action",
    # Errors
    "NotReadyError",
    "WriteInScopeError",
    "ServerError",
    # Primitives
    "create_signal",
    "create_memo",
    "create_effect",
    "create_tracked_effect",
    "create_render_effect",
    "on_settled",
    "on_cleanup",
    "create_root",
    "create_owner",
    "is_disposed",
    "is_server",
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
    "ChildrenAccessor",
    "create_reaction",
    # Lists
    "map_array",
    "repeat",
    # Misc
    "create_unique_id",
    "is_accessor",
]
