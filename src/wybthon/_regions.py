"""Mounted collection and branch regions for the virtual DOM renderer.

Preparation reads reactive inputs. Apply owns row creation, native ranges,
index updates, and disposal, so pending transitions never destroy resources
that still belong to the visible tree.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

from . import diagnostics
from .reactivity import _core
from .reactivity._core import Computation, Owner, Signal
from .store import StoreList, _wrap
from .vnode import VNode

_SCALARS = (str, int, float, bool, bytes, type(None), tuple, frozenset)


def _identity(value: Any) -> Any:
    if isinstance(value, _SCALARS):
        try:
            hash(value)
            return (0, value)
        except TypeError:
            pass
    return (1, id(value))


@dataclass(slots=True)
class _Input:
    source: Any
    data: Any
    revision: int = -1


@dataclass(slots=True, eq=False)
class _Row:
    owner: Owner
    item: Any
    value: Signal[Any] | None
    index: Signal[int]
    vnode: VNode
    key: Any


def _update_index(signal: Signal[int], index: int) -> None:
    if signal._value == index and not signal._staged:
        return
    if not signal._observers and not signal._staged and not _core._track and not _core._held:
        # An unused integer index has no propagation or transition work.
        # Keep its value current for a callback that starts reading it later.
        signal._value = index
    else:
        signal._commit_now(index)


class _ListRegion:
    __slots__ = (
        "vnode",
        "parent",
        "scope",
        "rows",
        "keyed",
        "callback",
        "fallback",
        "previous",
        "repeat",
        "start",
        "unique",
    )

    def __init__(self, vnode: VNode, parent: int) -> None:
        self.vnode, self.parent, self.scope = vnode, parent, vnode.scope
        self.rows: list[_Row] = []
        self.keyed = vnode.props.get("keyed", True)
        self.callback = vnode.props["children"]
        self.fallback: VNode | None = None
        self.previous: _Input | None = None
        self.repeat = vnode.props.get("repeat", False)
        self.start: int | None = None
        self.unique = True

    def prepare(self) -> _Input:
        value = self.vnode.props["source"]()
        if isinstance(value, StoreList):
            state = value._wyb_list_state()
            return _Input(value, state.data, state.revision)
        return _Input(value, () if value is None else value)

    def key(self, item: Any) -> Any:
        return self.keyed(item) if callable(self.keyed) else _identity(item)

    def new_row(self, item: Any, index: int, key: Any) -> _Row:
        from .reconciler import _coerce_result

        if diagnostics._active is not None:
            diagnostics._active.counts["rows_created"] += 1
        owner = Owner()
        self.scope._add_child(owner)
        item_signal = None if self.repeat or self.keyed is True else Signal(item)
        index_signal = Signal(index)
        try:
            args: tuple[Any, ...]
            if self.repeat:
                args = (item,)
            elif self.keyed is False:
                args = (item_signal, index)
            elif self.keyed is True:
                args = (item, index_signal)
            else:
                args = (item_signal, index_signal)
            result = _core._run_owned_untracked(owner, lambda: self.callback(*args))
            node = _coerce_result(result)
            node.owner_scope = owner
            return _Row(owner, item, item_signal, index_signal, node, key)
        except BaseException:
            owner.dispose()
            raise

    def update_row(self, row: _Row, item: Any, index: int) -> None:
        if row.item is not item:
            if row.value is not None:
                row.value._commit_now(item)
                # Equality can retain the previous object. Keep the cached
                # identity in sync so a later mutation of an equal replacement
                # still reaches the item accessor.
                row.item = row.value._value
            else:
                row.item = item
        if row.index._value != index or row.index._staged:
            _update_index(row.index, index)

    def dispose_row(self, row: _Row) -> None:
        from .reconciler import _unmount

        _unmount(row.vnode)
        row.owner.dispose()

    def drop_fallback(self) -> None:
        if self.fallback is not None:
            from .reconciler import _unmount

            _unmount(self.fallback)
            if self.fallback.owner_scope is not None:
                self.fallback.owner_scope.dispose()
            self.fallback = None
            self.vnode.children.clear()

    def show_fallback(self) -> None:
        from .flow import _render_slot
        from .reconciler import _coerce_result, mount

        fallback = self.vnode.props.get("fallback")
        if fallback is None or self.fallback is not None:
            return
        owner = Owner()
        self.scope._add_child(owner)
        try:
            self.fallback = _core._run_owned_untracked(owner, lambda: _coerce_result(_render_slot(fallback)))
            self.fallback.owner_scope = owner
            mount(self.fallback, self.parent, self.vnode._frag_end, self.vnode.ns)
            self.vnode.children[:] = [self.fallback]
        except BaseException:
            owner.dispose()
            raise

    def apply(self, value: _Input) -> None:
        old = self.previous
        if len(value.data):
            self.drop_fallback()
        if self.repeat:
            self.apply_count(value.data)
        elif old is not None and isinstance(value.source, StoreList) and value.source is old.source:
            changes = value.source._wyb_changes_since(old.revision)
            if changes is not None and self.apply_changes(changes, value.data):
                pass
            else:
                self.replace([_wrap(item) for item in value.data])
        else:
            data = [_wrap(item) for item in value.data] if isinstance(value.source, StoreList) else value.data
            self.replace(data)
        self.previous = value
        if not self.rows:
            self.show_fallback()

    def apply_count(self, values: range) -> None:
        start = values.start
        if self.start is not None and start != self.start:
            # The callback receives an ordinary int: a changed start recreates
            # slots instead of leaving stale values captured by run-once bodies.
            for row in self.rows:
                self.dispose_row(row)
            self.rows.clear()
            self.vnode.children.clear()
        self.start = start
        n = len(values)
        self.splice(min(n, len(self.rows)), max(0, len(self.rows) - n), values[len(self.rows) :])

    def apply_changes(self, changes: tuple[Any, ...], data: Any) -> bool:
        if not changes:
            return True
        # Journal edits already have their own incremental paths. A later
        # generic replacement must verify uniqueness again before trimming
        # a suffix, because an indexed edit can introduce duplicate keys.
        self.unique = False
        if diagnostics._active is not None:
            diagnostics._active.counts["list_edits"] += len(changes)
        if all(change.kind == "set" for change in changes):
            indices = sorted({change.index for change in changes})
            old_at = {i: self.rows[i] for i in indices}
            old_rows = list(old_at.values())
            available: dict[Any, deque[_Row]] = defaultdict(deque)
            for row in old_rows:
                available[row.key].append(row)
            reused = set()
            replacements = []
            for index in indices:
                item = _wrap(data[index])
                key = self.key(item)
                bucket = available.get(key)
                if self.keyed is False:
                    row = self.rows[index]
                    reused.add(row)
                elif bucket:
                    row = bucket.popleft()
                    reused.add(row)
                else:
                    row = self.new_row(item, index, key)
                self.update_row(row, item, index)
                replacements.append((index, row))
            from .reconciler import _first_dom_id, _move_range, mount

            # Replace the logical slots before deriving anchors for DOM moves.
            for index, row in replacements:
                self.rows[index] = row
                self.vnode.children[index] = row.vnode
            for index, row in reversed(replacements):
                anchor = (
                    _first_dom_id(self.rows[index + 1].vnode) if index + 1 < len(self.rows) else self.vnode._frag_end
                )
                if row.vnode.el is None:
                    mount(row.vnode, self.parent, anchor, self.vnode.ns)
                elif row is not old_at[index]:
                    _move_range(row.vnode, self.parent, anchor)
            for row in old_rows:
                if row not in reused:
                    self.dispose_row(row)
            return True
        if len(changes) == 1 and changes[0].kind == "splice":
            change = changes[0]
            self.splice(change.index, len(change.removed), [_wrap(item) for item in change.added])
            return True
        # Multiple tail edits can be replayed without walking existing rows.
        n = len(self.rows)
        for change in changes:
            if change.kind != "splice" or change.index + len(change.removed) != n:
                return False
            n += len(change.added) - len(change.removed)
        for change in changes:
            self.splice(change.index, len(change.removed), [_wrap(item) for item in change.added])
        return True

    def splice(self, start: int, delete: int, items: Any) -> None:
        if self.keyed is False and not self.repeat and start + delete < len(self.rows):
            # Positional rows represent slots, not entities. The final values
            # are supplied by replace's positional pass.
            data = [row.item for row in self.rows]
            data[start : start + delete] = items
            self.replace(data)
            return
        from .reconciler import _first_dom_id, _move_range, mount

        removed = self.rows[start : start + delete]
        available: dict[Any, deque[_Row]] = defaultdict(deque)
        for row in removed:
            available[row.key].append(row)
        added = []
        reused = set()
        for i, item in enumerate(items, start):
            key = self.key(item)
            bucket = available.get(key)
            if bucket and self.keyed is not False:
                row = bucket.popleft()
                reused.add(row)
                self.update_row(row, item, i)
            else:
                row = self.new_row(item, i, key)
            added.append(row)
        anchor = (
            _first_dom_id(self.rows[start + delete].vnode) if start + delete < len(self.rows) else self.vnode._frag_end
        )
        for row in added:
            if row.vnode.el is None:
                mount(row.vnode, self.parent, anchor, self.vnode.ns)
            else:
                _move_range(row.vnode, self.parent, anchor)
        for row in removed:
            if row not in reused:
                self.dispose_row(row)
        self.rows[start : start + delete] = added
        self.vnode.children[start : start + delete] = [row.vnode for row in added]
        if len(added) != delete:
            for i in range(start + len(added), len(self.rows)):
                _update_index(self.rows[i].index, i)
        if added:
            self.unique = len({row.key for row in added}) == len(added) if len(self.rows) == len(added) else False

    def replace(self, items: Any) -> None:
        if diagnostics._active is not None:
            diagnostics._active.counts["list_scanned"] += len(items)
        from .reconciler import _reconcile_children

        if self.keyed is False:
            common = min(len(self.rows), len(items))
            for i in range(common):
                self.update_row(self.rows[i], items[i], i)
            self.splice(common, len(self.rows) - common, items[common:])
            return
        # Retaining the unchanged prefix avoids rebuilding a matching table
        # for ordinary append/truncate operations. Match duplicates from the
        # front, preserving occurrence identity just like the general path.
        prefix = 0
        common = min(len(self.rows), len(items))
        while prefix < common:
            row, item = self.rows[prefix], items[prefix]
            if not (self.keyed is True and row.item is item) and row.key != self.key(item):
                break
            self.update_row(row, item, prefix)
            prefix += 1
        if prefix == common:
            self.splice(prefix, len(self.rows) - prefix, items[prefix:])
            return
        suffix = 0
        if self.unique:
            while suffix < common - prefix:
                row, item = self.rows[-1 - suffix], items[-1 - suffix]
                if not (self.keyed is True and row.item is item) and row.key != self.key(item):
                    break
                suffix += 1
            if suffix:
                middle_keys = {self.key(items[i]) for i in range(prefix, len(items) - suffix)}
                # A newly introduced duplicate must consume the old row at
                # its first occurrence, not reserve it for the suffix.
                if any(row.key in middle_keys for row in self.rows[len(self.rows) - suffix :]):
                    suffix = 0
        old_end, new_end = len(self.rows) - suffix, len(items) - suffix
        available: dict[Any, deque[_Row]] = defaultdict(deque)
        for row in self.rows[prefix:old_end]:
            available[row.key].append(row)
        next_rows = self.rows[:prefix]
        reused = set()
        for i in range(prefix, new_end):
            item = items[i]
            key = self.key(item)
            bucket = available.get(key)
            if bucket:
                row = bucket.popleft()
                reused.add(row)
                self.update_row(row, item, i)
            else:
                row = self.new_row(item, i, key)
                self.unique = False
            next_rows.append(row)
        for offset in range(suffix):
            row = self.rows[old_end + offset]
            self.update_row(row, items[new_end + offset], new_end + offset)
            next_rows.append(row)
        children = [row.vnode for row in next_rows]
        from .reconciler import _first_dom_id

        _reconcile_children(
            self.vnode.children[prefix:old_end],
            children[prefix:new_end],
            self.parent,
            _first_dom_id(children[new_end]) if suffix else self.vnode._frag_end,
            self.vnode.ns,
        )
        for row in self.rows[prefix:old_end]:
            if row not in reused:
                row.owner.dispose()
        self.rows = next_rows
        self.vnode.children = children


def mount_list(vnode: VNode, parent: int, anchor: int | None) -> None:
    """Mount a list region and its phased input subscription."""
    from .reconciler import _mount_fragment

    _mount_fragment(vnode, parent, anchor, vnode.ns)
    scope = vnode.scope = Owner()
    if _core._current_owner is not None:
        _core._current_owner._add_child(scope)
    region = _ListRegion(vnode, parent)
    vnode.props["_region"] = region
    comp = Computation(region.prepare, kind=_core._K_RENDER, apply_scope=False, apply=region.apply, pass_prev=False)
    scope._add_child(comp)
    vnode.render_effect = comp
    comp._update_if_necessary()


def mount_branch(vnode: VNode, parent: int, anchor: int | None) -> None:
    """Mount a selected branch, retaining its committed scope until replacement."""
    from .flow import _render_slot
    from .reconciler import _coerce_result, _mount_fragment, _unmount, mount

    _mount_fragment(vnode, parent, anchor, vnode.ns)
    scope = vnode.scope = Owner()
    if _core._current_owner is not None:
        _core._current_owner._add_child(scope)
    previous: list[Any] = [_core._MISSING]
    branch_owner: list[Owner | None] = [None]

    def apply(selection: Any) -> None:
        token, slot, args = selection
        if previous[0] is not _core._MISSING and not _core._changed(_core._DEFAULT_EQUALS, previous[0], token):
            return
        for child in vnode.children:
            _unmount(child)
        if branch_owner[0] is not None:
            branch_owner[0].dispose()
        owner = branch_owner[0] = Owner()
        scope._add_child(owner)
        try:
            node = _core._run_owned_untracked(owner, lambda: _coerce_result(_render_slot(slot, *args)))
            node.owner_scope = owner
            mount(node, parent, vnode._frag_end, vnode.ns)
            vnode.children[:] = [node]
            previous[0] = token
        except BaseException:
            owner.dispose()
            raise

    comp = Computation(vnode.props["choose"], kind=_core._K_RENDER, apply_scope=False, apply=apply, pass_prev=False)
    scope._add_child(comp)
    vnode.render_effect = comp
    comp._update_if_necessary()
