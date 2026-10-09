"""Reactive list mapping helpers.

[`map_array`][wybthon.map_array] turns a
reactive list into a memoized list of mapped rows, reusing each row's
owner scope across updates so per-row state survives reorders.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable, Sequence
from typing import Any

from . import _core
from ._core import Memo, Owner, Signal

__all__ = ["map_array", "repeat"]

# Scalar item types matched by value rather than identity in keyed mode.
_SCALAR = (str, int, float, bool, bytes, type(None), tuple, frozenset)


class _Row:
    __slots__ = ("owner", "item", "index", "result", "key")

    def __init__(self, owner: Owner, item: Signal[Any] | None, index: Signal[int], result: Any, key: Any) -> None:
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

    key_for = keyed if callable(keyed) else identity

    def compute() -> list[U]:
        nonlocal rows
        values = source()
        items: list[Any] = list(values) if values is not None else []
        if not items and fallback:
            items = [empty_key]

        # Append and truncate retain their prefix without allocating a deque
        # and matching-table entry for every existing row. Consume duplicate
        # keys from the front, as in the general occurrence-matching path.
        prefix = 0
        common = min(len(rows), len(items))
        next_key: Any = None
        while prefix < common:
            row, item = rows[prefix], items[prefix]
            next_key = empty_key if item is empty_key else prefix if keyed is False else key_for(item)
            if row.key != next_key:
                break
            if row.item is not None:
                row.item._set(item)
            if row.index._value != prefix or row.index._staged:
                row.index._set(prefix)
            prefix += 1
        available: dict[Any, deque[_Row]] = defaultdict(deque)
        for row in rows[prefix:]:
            available[row.key].append(row)
        prepared = rows[:prefix]
        for index in range(prefix, len(items)):
            item = items[index]
            key = (
                next_key
                if index == prefix and prefix < common
                else empty_key
                if item is empty_key
                else index
                if keyed is False
                else key_for(item)
            )
            bucket = available.get(key)
            if bucket:
                row = bucket.popleft()
                if row.item is not None:
                    row.item._set(item)
                if row.index._value != index or row.index._staged:
                    row.index._set(index)
            else:
                owner = Owner()
                scope._add_child(owner)
                item_signal = None if keyed is True else Signal(item)
                index_signal = Signal(index)
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


def repeat[U](
    count: Callable[[], int] | int,
    fn: Callable[[int], U],
    *,
    start: Callable[[], int] | int = 0,
    fallback: Callable[[], U] | None = None,
) -> Memo[list[U]]:
    """Map an integer range to rows, each with its own owner scope.

    The counterpart of Solid 2.0's `repeat`: `fn(i)` runs once per slot
    for `i` in `range(start, start + count)`. Growing the count maps only
    the new slots; shrinking it disposes the removed ones. Changing
    `start` maps every slot again, because each row received a plain int.

    Args:
        count: The number of slots, or an accessor for it.
        fn: Maps one slot number to a row.
        start: The first slot number, or an accessor for it.
        fallback: Optional zero-arg callable whose result is the single
            row when the count is zero.

    Returns:
        A [`Memo`][wybthon.Memo] yielding the list of mapped rows.
    """

    def slots() -> range:
        n = count() if callable(count) else count
        first = start() if callable(start) else start
        return range(first, first + max(0, int(n)))

    return map_array(slots, lambda i, _index: fn(i), fallback=fallback)
