"""Reactive list mapping and selection helpers.

[`map_array`][wybthon.map_array] turns a
reactive list into a memoized list of mapped rows, reusing each row's
owner scope across updates so per-row state survives reorders.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable, Sequence
from typing import Any

from . import _core
from ._core import Accessor, Memo, Owner, Signal

__all__ = ["map_array", "create_selector"]

# Scalar item types matched by value rather than identity in keyed mode.
_SCALAR = (str, int, float, bool, bytes, type(None), tuple, frozenset)


class _Row:
    __slots__ = ("owner", "item", "index", "result", "key")

    def __init__(self, owner: Owner, item: Signal[Any], index: Signal[int], result: Any, key: Any) -> None:
        self.owner = owner
        self.item = item
        self.index = index
        self.result = result
        self.key = key


def _run_row[T](owner: Owner, fn: Callable[..., T], *args: Any) -> T:
    return _core._run_owned_untracked(owner, lambda: fn(*args))


def map_array[T, U](
    source: Callable[[], Sequence[T] | None],
    fn: Callable[..., U],
    *,
    keyed: bool | Callable[[T], Any] = True,
    fallback: Callable[[], U] | None = None,
) -> Memo[list[U]]:
    """Map a reactive list to mapped rows with per-row owner scopes.

    Rows are matched between updates according to `keyed`:

    - `True` (default): match by **identity** (scalars by value). A
      matched row keeps its scope and mapped result and its index
      accessor updates. `fn(item, index)` receives the raw item and an
      `Accessor[int]`.
    - `False`: match by **position**. The row at each index is reused
      and its item accessor updates. `fn(item, index)` receives an
      `Accessor[T]` and an `int`.
    - a callable `key(item) -> hashable`: match by key. Both item and
      index are accessors: `fn(item, index)` receives `Accessor[T]` and
      `Accessor[int]`.

    Row bodies run **untracked** inside the row's owner; anything
    reactive inside a row must read an accessor within a hole, memo, or
    effect, and cleanups registered with `on_cleanup` run when the row is
    removed.

    Args:
        source: Zero-arg accessor returning the list (or `None`).
        fn: Row mapping function; see the shapes above.
        keyed: Matching strategy.
        fallback: Optional zero-arg callable whose result is the single
            row when the list is empty.

    Returns:
        A [`Memo`][wybthon.Memo] yielding the list of mapped rows.
    """
    scope = Owner()
    if _core._current_owner is not None:
        _core._current_owner._add_child(scope)
    rows: list[_Row] = []
    allocated: set[_Row] = set()
    empty_key = object()

    def identity(item: Any) -> Any:
        if isinstance(item, _SCALAR):
            try:
                hash(item)
                return (0, item)
            except TypeError:
                pass
        return (1, id(item))

    def compute() -> list[U]:
        nonlocal rows
        values = source()
        items = list(values) if values is not None else []
        entries: list[tuple[int, Any]] = list(enumerate(items)) if items else ([(0, empty_key)] if fallback else [])
        available: dict[Any, deque[_Row]] = defaultdict(deque)
        for row in rows:
            available[row.key].append(row)
        prepared = []
        for index, item in entries:
            key = (
                empty_key
                if item is empty_key
                else (index if keyed is False else keyed(item) if callable(keyed) else identity(item))
            )
            bucket = available[key]
            if bucket:
                row = bucket.popleft()
                row.item._set(item)
                row.index._set(index)
            else:
                owner = Owner()
                scope._add_child(owner)
                item_signal, index_signal = Signal(item), Signal(index)
                try:
                    if item is empty_key:
                        result = _run_row(owner, fallback)
                    elif keyed is False:
                        result = _run_row(owner, fn, item_signal, index)
                    elif keyed is True:
                        result = _run_row(owner, fn, item, index_signal)
                    else:
                        result = _run_row(owner, fn, item_signal, index_signal)
                except BaseException:
                    owner.dispose()
                    raise
                row = _Row(owner, item_signal, index_signal, result, key)
                allocated.add(row)
            prepared.append(row)
        rows = prepared
        return [row.result for row in rows]

    mapped = _MappedMemo(compute, scope)

    def prepare_disposal() -> set[_Row]:
        mapped()
        return set(rows)

    def commit_disposal(visible: set[_Row]) -> None:
        for row in allocated - visible:
            row.owner.dispose()
            allocated.remove(row)

    # Row resources survive speculative recomputation. Cleanup follows the
    # same visible apply phase as DOM regions, including held transitions.
    cleanup = _core.Computation(
        prepare_disposal, kind=_core._K_RENDER, apply=commit_disposal, apply_scope=False, pass_prev=False
    )
    scope._add_child(cleanup)
    scope._add_cleanup(mapped.dispose)
    cleanup._update_if_necessary()
    return mapped


class _MappedMemo[T](Memo[T]):
    __slots__ = ("_row_scope",)

    def __init__(self, compute: Callable[[], T], scope: Owner) -> None:
        self._row_scope = scope
        super().__init__(compute, equals=False)

    def dispose(self) -> None:
        """Dispose the mapped value and every retained row resource."""
        if self._disposed:
            return
        super().dispose()
        self._row_scope.dispose()


def create_selector[T](
    source: Callable[[], T],
    equals: Callable[[T, Any], bool] | None = None,
) -> Callable[[Any], bool]:
    """Return `is_selected(key)`: a tracked boolean that only updates the affected keys.

    A naive `lambda: item.id == selected()` in every row re-runs every
    row when the selection changes. `create_selector` subscribes each
    key once and only notifies the row that was selected and the one
    that was deselected.

    Args:
        source: Accessor for the current selection.
        equals: Optional `(selection, key) -> bool` comparison.

    Returns:
        A function `key -> bool` to call inside a hole, memo, or effect.
    """
    subs: dict[Any, Signal[bool]] = {}
    current: Signal[Any] = Signal(_core._MISSING)

    def update(value: T) -> None:
        prev = current._latest()
        current._set(value)
        if equals is None:
            try:
                keys = {prev, value}
                affected = [(key, subs[key]) for key in keys if key in subs]
            except TypeError:
                affected = list(subs.items())
        else:
            affected = list(subs.items())
        for key, sig in affected:
            now = equals(value, key) if equals else (value == key)
            sig._set(now)

    # Eager: the apply stage writes graph data (the per-key flags), so it
    # runs immediately and its writes are held with the selection when a
    # transition holds it.
    comp = _core.Computation(source, kind=_core._K_RENDER, apply_scope=False, apply=update, pass_prev=False, eager=True)
    owner = _core._current_owner
    if owner is not None:
        owner._add_child(comp)
    comp._update_if_necessary()

    def is_selected(key: Any) -> bool:
        value = current.peek()
        init = (equals(value, key) if equals else (value == key)) if value is not _core._MISSING else False
        if _core._current_observer is None:
            return bool(init)
        sig = subs.get(key)
        if sig is None:

            def release() -> None:
                if subs.get(key) is sig and not sig._observers:
                    subs.pop(key, None)

            working = current._value
            sig = Signal(bool(equals(working, key) if equals else working == key), unobserved=release)
            if current in _core._held:
                shown = _core._held[current]
                _core._hold(sig, bool(equals(shown, key) if equals else shown == key))
            subs[key] = sig
        return sig()

    return is_selected


def _accessor_of(value: Any) -> Accessor[Any]:
    """Wrap any zero-arg callable as an Accessor (identity for existing accessors)."""
    if isinstance(value, Accessor):
        return value
    return _Fn(value)


class _Fn[T](Accessor[T]):
    __slots__ = ("_fn",)

    def __init__(self, fn: Callable[[], T]) -> None:
        self._fn = fn

    def __call__(self) -> T:
        return self._fn()

    def peek(self) -> T:
        return _core.untrack(self._fn)
