"""Reactive list mapping and selection helpers.

[`map_array`][wybthon.map_array] is the engine behind
[`For`][wybthon.For] and [`Repeat`][wybthon.Repeat]: it turns a
reactive list into a memoized list of mapped rows, reusing each row's
owner scope across updates so per-row state survives reorders.
"""

from __future__ import annotations

from collections.abc import Callable
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
    source: Callable[[], list[T] | None],
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
    if keyed is True:
        return _map_identity(source, fn, fallback)
    if keyed is False:
        return _map_positional(source, fn, fallback)
    return _map_keyed(source, fn, keyed, fallback)


def _dispose_rows(rows: list[_Row]) -> None:
    for row in rows:
        row.owner.dispose()


def _map_identity[T, U](
    source: Callable[[], list[T] | None],
    fn: Callable[..., U],
    fallback: Callable[[], U] | None,
) -> Memo[list[U]]:
    rows: list[_Row] = []
    fallback_row: list[_Row] = []
    parent_owner = _core._current_owner

    def dispose_all() -> None:
        _dispose_rows(rows)
        rows.clear()
        _dispose_rows(fallback_row)
        fallback_row.clear()

    if parent_owner is not None:
        parent_owner._add_cleanup(dispose_all)

    def compute() -> list[U]:
        new_items = source() or []
        if not new_items:
            _dispose_rows(rows)
            rows.clear()
            if fallback is not None:
                if not fallback_row:
                    owner = Owner()
                    if parent_owner is not None:
                        parent_owner._add_child(owner)
                    result = _run_row(owner, fallback)
                    fallback_row.append(_Row(owner, Signal(None), Signal(0), result, None))
                return [fallback_row[0].result]
            return []
        if fallback_row:
            _dispose_rows(fallback_row)
            fallback_row.clear()

        by_identity: dict[int, list[_Row]] = {}
        by_value: dict[Any, list[_Row]] = {}
        for old in rows:
            item = old.item._value
            if isinstance(item, _SCALAR):
                try:
                    by_value.setdefault(item, []).append(old)
                    continue
                except TypeError:
                    pass
            by_identity.setdefault(id(item), []).append(old)

        new_rows: list[_Row] = []
        reused: set[int] = set()
        for index, item in enumerate(new_items):
            row: _Row
            bucket: list[_Row] | None = None
            if isinstance(item, _SCALAR):
                try:
                    bucket = by_value.get(item)
                except TypeError:
                    bucket = None
            if bucket is None:
                bucket = by_identity.get(id(item))
            if bucket:
                row = bucket.pop(0)
                if row.index._value != index:
                    row.index._commit_now(index)
                reused.add(id(row))
            else:
                owner = Owner()
                if parent_owner is not None:
                    parent_owner._add_child(owner)
                index_sig: Signal[int] = Signal(index)
                result = _run_row(owner, fn, item, index_sig)
                row = _Row(owner, Signal(item), index_sig, result, None)
            new_rows.append(row)
        for old in rows:
            if id(old) not in reused:
                old.owner.dispose()
        rows[:] = new_rows
        return [r.result for r in new_rows]

    return Memo(compute, equals=False)


def _map_positional[T, U](
    source: Callable[[], list[T] | None],
    fn: Callable[..., U],
    fallback: Callable[[], U] | None,
) -> Memo[list[U]]:
    rows: list[_Row] = []
    fallback_row: list[_Row] = []
    parent_owner = _core._current_owner

    def dispose_all() -> None:
        _dispose_rows(rows)
        rows.clear()
        _dispose_rows(fallback_row)
        fallback_row.clear()

    if parent_owner is not None:
        parent_owner._add_cleanup(dispose_all)

    def compute() -> list[U]:
        new_items = source() or []
        if not new_items:
            _dispose_rows(rows)
            rows.clear()
            if fallback is not None:
                if not fallback_row:
                    owner = Owner()
                    if parent_owner is not None:
                        parent_owner._add_child(owner)
                    result = _run_row(owner, fallback)
                    fallback_row.append(_Row(owner, Signal(None), Signal(0), result, None))
                return [fallback_row[0].result]
            return []
        if fallback_row:
            _dispose_rows(fallback_row)
            fallback_row.clear()

        n_old = len(rows)
        n_new = len(new_items)
        for i in range(min(n_old, n_new)):
            rows[i].item._commit_now(new_items[i])
        if n_new < n_old:
            _dispose_rows(rows[n_new:])
            del rows[n_new:]
        else:
            for i in range(n_old, n_new):
                owner = Owner()
                if parent_owner is not None:
                    parent_owner._add_child(owner)
                item_sig: Signal[Any] = Signal(new_items[i])
                result = _run_row(owner, fn, item_sig, i)
                rows.append(_Row(owner, item_sig, Signal(i), result, None))
        return [row.result for row in rows]

    return Memo(compute, equals=False)


def _map_keyed[T, U](
    source: Callable[[], list[T] | None],
    fn: Callable[..., U],
    key_fn: Callable[[T], Any],
    fallback: Callable[[], U] | None,
) -> Memo[list[U]]:
    rows: list[_Row] = []
    fallback_row: list[_Row] = []
    parent_owner = _core._current_owner

    def dispose_all() -> None:
        _dispose_rows(rows)
        rows.clear()
        _dispose_rows(fallback_row)
        fallback_row.clear()

    if parent_owner is not None:
        parent_owner._add_cleanup(dispose_all)

    def compute() -> list[U]:
        new_items = source() or []
        if not new_items:
            _dispose_rows(rows)
            rows.clear()
            if fallback is not None:
                if not fallback_row:
                    owner = Owner()
                    if parent_owner is not None:
                        parent_owner._add_child(owner)
                    result = _run_row(owner, fallback)
                    fallback_row.append(_Row(owner, Signal(None), Signal(0), result, None))
                return [fallback_row[0].result]
            return []
        if fallback_row:
            _dispose_rows(fallback_row)
            fallback_row.clear()

        by_key: dict[Any, _Row] = {row.key: row for row in rows}
        new_rows: list[_Row] = []
        reused: set[int] = set()
        for index, item in enumerate(new_items):
            key = key_fn(item)
            row = by_key.get(key)
            if row is not None and id(row) not in reused:
                reused.add(id(row))
                if row.item._value is not item:
                    row.item._commit_now(item)
                if row.index._value != index:
                    row.index._commit_now(index)
            else:
                owner = Owner()
                if parent_owner is not None:
                    parent_owner._add_child(owner)
                item_sig: Signal[Any] = Signal(item)
                index_sig: Signal[int] = Signal(index)
                result = _run_row(owner, fn, item_sig, index_sig)
                row = _Row(owner, item_sig, index_sig, result, key)
            new_rows.append(row)
        for row in rows:
            if id(row) not in reused:
                row.owner.dispose()
        rows[:] = new_rows
        return [row.result for row in new_rows]

    return Memo(compute, equals=False)


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
    current: list[Any] = [_core._MISSING]

    def update(value: T) -> None:
        prev = current[0]
        current[0] = value
        for key, sig in subs.items():
            now = equals(value, key) if equals else (value == key)
            was = (equals(prev, key) if equals else (prev == key)) if prev is not _core._MISSING else False
            if now != was:
                sig._set(now)

    # Eager: the apply stage writes graph data (the per-key flags), so it
    # runs immediately and its writes are held with the selection when a
    # transition holds it.
    comp = _core.Computation(source, kind=_core._K_RENDER, apply=update, pass_prev=False, eager=True)
    owner = _core._current_owner
    if owner is not None:
        owner._add_child(comp)
    comp._update_if_necessary()

    def is_selected(key: Any) -> bool:
        sig = subs.get(key)
        if sig is None:
            value = current[0]
            init = (equals(value, key) if equals else (value == key)) if value is not _core._MISSING else False
            sig = Signal(init)
            subs[key] = sig
            reader = _core._current_owner
            if reader is not None:
                reader._add_cleanup(lambda: subs.pop(key, None) if subs.get(key) is sig else None)
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
