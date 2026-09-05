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
    item: Signal[Any]
    index: Signal[int]
    vnode: VNode
    key: Any


class _ListRegion:
    __slots__ = ("vnode", "parent", "scope", "rows", "keyed", "callback", "fallback", "previous", "repeat", "start")

    def __init__(self, vnode: VNode, parent: int) -> None:
        self.vnode, self.parent, self.scope = vnode, parent, vnode.scope
        self.rows: list[_Row] = []
        self.keyed = vnode.props.get("keyed", True)
        self.callback = vnode.props["children"]
        self.fallback: VNode | None = None
        self.previous: _Input | None = None
        self.repeat = vnode.props.get("repeat", False)
        self.start: int | None = None

    def prepare(self) -> _Input:
        value = self.vnode.props["source"]()
        if isinstance(value, StoreList):
            state = value._wyb_list_state()
            return _Input(value, state.data, state.revision)
        return _Input(value, () if value is None else value)

    def key(self, item: Any) -> Any:
        return self.keyed(item) if callable(self.keyed) else _identity(item)

    def new_row(self, item: Any, index: int) -> _Row:
        from .reconciler import _coerce_result

        if diagnostics._active is not None:
            diagnostics._active.counts["rows_created"] += 1
        owner = Owner()
        self.scope._add_child(owner)
        item_signal, index_signal = Signal(item), Signal(index)
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
            return _Row(owner, item_signal, index_signal, node, self.key(item))
        except BaseException:
            owner.dispose()
            raise

    def update_row(self, row: _Row, item: Any, index: int) -> None:
        row.item._commit_now(item)
        row.index._commit_now(index)

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
                bucket = available[self.key(item)]
                if self.keyed is False:
                    row = self.rows[index]
                    reused.add(row)
                elif bucket:
                    row = bucket.popleft()
                    reused.add(row)
                else:
                    row = self.new_row(item, index)
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
            data = [row.item._value for row in self.rows]
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
            bucket = available[self.key(item)]
            if bucket and self.keyed is not False:
                row = bucket.popleft()
                reused.add(row)
                self.update_row(row, item, i)
            else:
                row = self.new_row(item, i)
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
                self.rows[i].index._commit_now(i)

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
        available: dict[Any, deque[_Row]] = defaultdict(deque)
        for row in self.rows:
            available[row.key].append(row)
        next_rows = []
        reused = set()
        for i, item in enumerate(items):
            bucket = available[self.key(item)]
            if bucket:
                row = bucket.popleft()
                reused.add(row)
                self.update_row(row, item, i)
            else:
                row = self.new_row(item, i)
            next_rows.append(row)
        children = [row.vnode for row in next_rows]
        _reconcile_children(self.vnode.children, children, self.parent, self.vnode._frag_end, self.vnode.ns)
        for row in self.rows:
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
