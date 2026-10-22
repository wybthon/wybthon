"""Mounted collection and branch regions for the virtual DOM renderer.

Preparation reads reactive inputs. Apply owns row creation, native ranges,
index updates, and disposal, so pending transitions never destroy resources
that still belong to the visible tree.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

from . import diagnostics, kernel, reconciler, templates
from .kernel import OP_DISPOSE_RANGE
from .reactivity import _core
from .reactivity._core import Accessor, Computation, Owner, Signal, _CallbackScope, _read, _run_callback_body
from .vnode import VNode

_SCALARS = (str, int, float, bool, bytes, type(None), tuple, frozenset)

# Store list support, registered by ``wybthon.store`` when it's imported. A
# page that never imports stores can't produce a store list, so list regions
# don't import the store module themselves (it's a sizable part of startup).
StoreList: Any = type("_NoStoreList", (), {})


def _wrap(value: Any) -> Any:
    return value


def register_store(store_list: type, wrap: Any) -> None:
    """Called by ``wybthon.store`` on import: enables incremental store list updates."""
    global StoreList, _wrap
    StoreList = store_list
    _wrap = wrap


_FOR_SCOPE = _CallbackScope("For")
_REPEAT_SCOPE = _CallbackScope("Repeat")
_BRANCH_SCOPE = _CallbackScope("Show or Match")


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


class _Row(Owner, Accessor[int]):
    """A mounted list row: the owner of its subtree, and its own index accessor.

    The row callback receives the row as its index accessor. The index is
    a plain integer until something reads it in a tracking scope; only
    then is the signal behind it created, so a row whose callback never
    reads its index (most rows) allocates nothing for it.
    """

    __slots__ = ("item", "value", "_index", "_index_signal", "vnode", "key")

    def __init__(self, item: Any, value: Signal[Any] | None, index: int, key: Any) -> None:
        # Owner's fields, assigned directly (one row per list item); keep
        # in sync with `Owner.__init__`.
        self._tasks = None
        self._parent = None
        self._provisional = None
        self._children = None
        self._cleanups = None
        self._disposed = False
        self._context_map = None
        self._error_handler = None
        self.item = item
        self.value = value
        self._index = index
        self._index_signal: Signal[int] | None = None
        self.vnode: VNode | None = None
        self.key = key

    def __call__(self) -> int:
        sig = self._index_signal
        if sig is None:
            if _core._current_observer is None:
                if _core._setup_depth and not _core._untrack_depth:
                    _core._warn_top_level_read(self)
                return self._index
            sig = self._index_signal = Signal(self._index)
        return sig()

    def peek(self) -> int:
        sig = self._index_signal
        return self._index if sig is None else sig.peek()

    def _label(self) -> str:
        return "the row index"


def _update_index(row: _Row, index: int) -> None:
    if row._index == index:
        sig = row._index_signal
        if sig is None or not sig._staged:
            return
    row._index = index
    signal = row._index_signal
    if signal is None:
        return
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
        "source",
        "cell",
    )

    def __init__(self, vnode: VNode, parent: int) -> None:
        self.vnode, self.parent, self.scope = vnode, parent, vnode.scope
        self.source = vnode.props["source"]
        # A region a re-rendering hole can patch reads its source through a
        # signal, so a new source can be pushed in (see ``patch_region``).
        self.cell: Signal[Any] | None = Signal(self.source) if reconciler._patchable else None
        self.rows: list[_Row] = []
        self.keyed = vnode.props.get("keyed", True)
        self.callback = vnode.props["children"]
        self.fallback: VNode | None = None
        self.previous: _Input | None = None
        self.repeat = vnode.props.get("repeat", False)
        self.start: int | None = None
        self.unique = True

    def prepare(self) -> _Input:
        cell = self.cell
        source = cell() if cell is not None else self.source
        if self.repeat:
            count, start = source
            n = max(0, int(_read(count) or 0))
            first = int(_read(start) or 0)
            return _Input(source, range(first, first + n))
        value = _read(source)
        if isinstance(value, StoreList):
            state = value._wyb_list_state()
            return _Input(value, state.data, state.revision)
        return _Input(value, () if value is None else value)

    def key(self, item: Any) -> Any:
        return self.keyed(item) if callable(self.keyed) else _identity(item)

    def new_row(self, item: Any, index: int, key: Any) -> _Row:
        if diagnostics._active is not None:
            diagnostics._active.counts["rows_created"] += 1
        item_signal = None if self.repeat or self.keyed is True else Signal(item)
        owner = _Row(item, item_signal, index, key)
        self.scope._add_child(owner)
        try:
            args: tuple[Any, ...]
            if self.repeat:
                args = (item,)
            elif self.keyed is False:
                args = (item_signal, index)
            elif self.keyed is True:
                args = (item, owner)
            else:
                args = (item_signal, owner)
            scope = _REPEAT_SCOPE if self.repeat else _FOR_SCOPE
            session = _core._session
            if session is not None and session.keying:
                position = f"{getattr(self.vnode, 'pk', None) or _core._position}.{index}"
                previous = _core._enter_position(position)
                try:
                    result = _run_callback_body(owner, scope, lambda: self.callback(*args))
                finally:
                    _core._restore_position(previous)
                node = reconciler._coerce_result(result)
                node.pk = position
            else:
                node = reconciler._coerce_result(_run_callback_body(owner, scope, lambda: self.callback(*args)))
            node.owner_scope = owner
            owner.vnode = node
            return owner
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
        _update_index(row, index)

    def dispose_row(self, row: _Row) -> None:
        self._dispose_rows([row])

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
            # Replace the logical slots before deriving anchors for DOM moves.
            for index, row in replacements:
                self.rows[index] = row
                self.vnode.children[index] = row.vnode
            for index, row in reversed(replacements):
                anchor = (
                    reconciler._first_dom_id(self.rows[index + 1].vnode)
                    if index + 1 < len(self.rows)
                    else self.vnode._frag_end
                )
                if row.vnode.el is None:
                    reconciler.mount(row.vnode, self.parent, anchor, self.vnode.ns)
                elif row is not old_at[index]:
                    reconciler._move_range(row.vnode, self.parent, anchor)
            for row in old_rows:
                if row not in reused:
                    self.dispose_row(row)
            return True
        if len(changes) == 1 and changes[0].kind in ("splice", "clear"):
            change = changes[0]
            self.splice(
                change.index,
                len(change.removed),
                [_wrap(item) for item in change.added],
                reverse_disposal=change.kind == "clear",
            )
            return True
        # Multiple tail edits can be replayed without walking existing rows.
        n = len(self.rows)
        for change in changes:
            if change.kind not in ("splice", "clear") or change.index + len(change.removed) != n:
                return False
            n += len(change.added) - len(change.removed)
        for change in changes:
            self.splice(
                change.index,
                len(change.removed),
                [_wrap(item) for item in change.added],
                reverse_disposal=change.kind == "clear",
            )
        return True

    def splice(self, start: int, delete: int, items: Any, *, reverse_disposal: bool = False) -> None:
        if self.keyed is False and not self.repeat and start + delete < len(self.rows):
            # Positional rows represent slots, not entities. The final values
            # are supplied by replace's positional pass.
            data = [row.item for row in self.rows]
            data[start : start + delete] = items
            self.replace(data)
            return
        if start == 0 and delete == len(self.rows) and delete and not len(items):
            self.clear(reverse_disposal)
            return
        removed = self.rows[start : start + delete]
        available: dict[Any, deque[_Row]] = defaultdict(deque)
        if len(items):
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
            reconciler._first_dom_id(self.rows[start + delete].vnode)
            if start + delete < len(self.rows)
            else self.vnode._frag_end
        )
        for row in added:
            if row.vnode.el is None:
                reconciler.mount(row.vnode, self.parent, anchor, self.vnode.ns)
            else:
                reconciler._move_range(row.vnode, self.parent, anchor)
        # MutableSequence.clear() previously popped from the end. A single
        # clear edit must preserve that observable row cleanup order.
        for row in reversed(removed) if reverse_disposal else removed:
            if row not in reused:
                self.dispose_row(row)
        self.rows[start : start + delete] = added
        self.vnode.children[start : start + delete] = [row.vnode for row in added]
        if len(added) != delete:
            for i in range(start + len(added), len(self.rows)):
                _update_index(self.rows[i], i)
        if added:
            self.unique = len({row.key for row in added}) == len(added) if len(self.rows) == len(added) else False

    def clear(self, reverse_disposal: bool = False) -> None:
        """Remove every row with one native range disposal."""
        rows = self.rows
        self._dispose_rows(rows, reverse_disposal)
        self.rows = []
        self.vnode.children = []
        self.unique = True

    def _dispose_rows(self, rows: list[_Row], reverse: bool = False) -> None:
        """Dispose a contiguous run of mounted rows with one range command."""
        _dispose_tree = reconciler._dispose_tree
        _range_bounds = reconciler._range_bounds
        first, _ = _range_bounds(rows[0].vnode)
        _, last = _range_bounds(rows[-1].vnode)
        if first is not None and last is not None:
            kernel.emit((OP_DISPOSE_RANGE, first, last))
        dispose_template = templates.dispose
        for row in reversed(rows) if reverse else rows:
            vnode = row.vnode
            # The row's owner disposes its computations and scopes.
            if vnode.tag == "_tpl":
                if vnode.subtree is None:
                    dispose_template(vnode, True)
                else:
                    _dispose_tree(vnode)
            else:
                _dispose_tree(vnode)
            row.dispose()

    def replace(self, items: Any) -> None:
        if diagnostics._active is not None:
            diagnostics._active.counts["list_scanned"] += len(items)
        if self.keyed is False:
            common = min(len(self.rows), len(items))
            for i in range(common):
                self.update_row(self.rows[i], items[i], i)
            self.splice(common, len(self.rows) - common, items[common:])
            return
        rows = self.rows
        common = min(len(rows), len(items))
        # Retaining the unchanged prefix avoids rebuilding a matching table
        # for ordinary append/truncate operations. Match duplicates from the
        # front, preserving occurrence identity just like the general path.
        # Rows matched by identity at the same position need no update.
        prefix = 0
        if self.keyed is True:
            while prefix < common and rows[prefix].item is items[prefix]:
                prefix += 1
        while prefix < common:
            row, item = rows[prefix], items[prefix]
            if not (self.keyed is True and row.item is item) and row.key != self.key(item):
                break
            self.update_row(row, item, prefix)
            prefix += 1
        if prefix == common:
            self.splice(prefix, len(rows) - prefix, items[prefix:])
            return
        suffix = 0
        if self.unique:
            limit = common - prefix
            if self.keyed is True:
                while suffix < limit and rows[-1 - suffix].item is items[-1 - suffix]:
                    suffix += 1
            while suffix < limit:
                row, item = rows[-1 - suffix], items[-1 - suffix]
                if not (self.keyed is True and row.item is item) and row.key != self.key(item):
                    break
                suffix += 1
            if suffix and len(items) - suffix > prefix:
                middle_keys = {self.key(items[i]) for i in range(prefix, len(items) - suffix)}
                # A newly introduced duplicate must consume the old row at
                # its first occurrence, not reserve it for the suffix.
                if any(row.key in middle_keys for row in rows[len(rows) - suffix :]):
                    suffix = 0
        old_end, new_end = len(rows) - suffix, len(items) - suffix
        if self._swap_ends(items, prefix, old_end, new_end):
            return
        available: dict[Any, deque[_Row]] = defaultdict(deque)
        for row in rows[prefix:old_end]:
            available[row.key].append(row)
        next_rows = rows[:prefix]
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
        shift = new_end - old_end
        if suffix:
            tail = rows[old_end:]
            if shift or self.keyed is not True:
                for offset, row in enumerate(tail):
                    index = new_end + offset
                    item = items[index]
                    if row.item is item and row._index_signal is None:
                        # An index nothing has read is a plain integer.
                        row._index = index
                    else:
                        self.update_row(row, item, index)
            next_rows.extend(tail)
        children = [row.vnode for row in next_rows]
        if not reused and not prefix and not suffix:
            # Nothing was kept: mount the new rows as one run, then dispose
            # the old ones with a single range instead of matching pairs.
            old_rows = rows
            end = self.vnode._frag_end
            parent, ns = self.parent, self.vnode.ns
            for row in next_rows:
                reconciler.mount(row.vnode, parent, end, ns)
            self._dispose_rows(old_rows)
            self.rows = next_rows
            self.vnode.children = children
            return
        reconciler._reconcile_children(
            self.vnode.children[prefix:old_end],
            children[prefix:new_end],
            self.parent,
            reconciler._first_dom_id(children[new_end]) if suffix else self.vnode._frag_end,
            self.vnode.ns,
        )
        for row in rows[prefix:old_end]:
            if row not in reused:
                row.dispose()
        self.rows = next_rows
        self.vnode.children = children

    def _swap_ends(self, items: Any, start: int, old_end: int, new_end: int) -> bool:
        """Apply a replacement that only swapped the first and last rows of the changed run.

        Solid's `reconcileArrays` special-cases the same move: two native
        moves and two index updates, instead of matching the whole run.
        Returns False (nothing changed) when the run isn't such a swap.
        """
        rows = self.rows
        last = old_end - 1
        if old_end != new_end or last - start < 1 or self.keyed is not True:
            return False
        first_row, last_row = rows[start], rows[last]
        if first_row.item is not items[last] or last_row.item is not items[start]:
            return False
        for i in range(start + 1, last):
            if rows[i].item is not items[i]:
                return False
        children = self.vnode.children
        after = reconciler._first_dom_id(rows[old_end].vnode) if old_end < len(rows) else self.vnode._frag_end
        reconciler._move_range(last_row.vnode, self.parent, reconciler._first_dom_id(first_row.vnode))
        reconciler._move_range(first_row.vnode, self.parent, after)
        rows[start], rows[last] = last_row, first_row
        children[start], children[last] = children[last], children[start]
        _update_index(last_row, start)
        _update_index(first_row, last)
        return True


def mount_list(vnode: VNode, parent: int, anchor: int | None) -> None:
    """Mount a list region and its phased input subscription."""
    from .reconciler import _close_fragment, _open_fragment

    claim_end = _open_fragment(vnode, parent, anchor)
    scope = vnode.scope = Owner()
    if _core._current_owner is not None:
        _core._current_owner._add_child(scope)
    region = _ListRegion(vnode, parent)
    vnode.props["_region"] = region
    comp = Computation(region.prepare, kind=_core._K_RENDER, apply_scope=False, apply=region.apply, pass_prev=False)
    scope._add_child(comp)
    vnode.render_effect = comp
    comp._update_if_necessary()
    if claim_end:
        _close_fragment(vnode, parent)


def mount_branch(vnode: VNode, parent: int, anchor: int | None) -> None:
    """Mount a selected branch, retaining its committed scope until replacement.

    The branch's `select(inputs, current)` returns `(token, slot, args)`;
    the content re-mounts only when the token changes. `current` reads the
    latest inputs (a signal when the region can be patched).
    """
    from .flow import _render_slot
    from .reconciler import _close_fragment, _coerce_result, _open_fragment, _unmount

    select = vnode.props["select"]
    inputs = vnode.props["inputs"]
    if reconciler._patchable:
        cell: Signal[Any] = Signal(inputs)
        vnode.props["_cell"] = cell

        def choose() -> Any:
            return select(cell(), cell)

    else:

        def current() -> Any:
            return inputs

        def choose() -> Any:
            return select(inputs, current)

    claim_end = _open_fragment(vnode, parent, anchor)
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
            session = _core._session
            if session is not None and session.keying:
                position = f"{getattr(vnode, 'pk', None) or _core._position}.{token[0]}"
                outer_position = _core._enter_position(position)
                try:
                    node = _run_callback_body(owner, _BRANCH_SCOPE, lambda: _coerce_result(_render_slot(slot, *args)))
                finally:
                    _core._restore_position(outer_position)
                node.pk = position
            else:
                node = _run_callback_body(owner, _BRANCH_SCOPE, lambda: _coerce_result(_render_slot(slot, *args)))
            node.owner_scope = owner
            reconciler.mount(node, parent, vnode._frag_end, vnode.ns)
            vnode.children[:] = [node]
            previous[0] = token
        except BaseException:
            owner.dispose()
            raise

    comp = Computation(choose, kind=_core._K_RENDER, apply_scope=False, apply=apply, pass_prev=False)
    scope._add_child(comp)
    vnode.render_effect = comp
    comp._update_if_necessary()
    if claim_end:
        _close_fragment(vnode, parent)


def patch_region(old: VNode, new: VNode) -> bool:
    """Push a re-rendered region's new condition or source into the mounted one.

    Returns False (the caller replaces the region) when the two aren't
    the same kind of region, or the mounted one can't be patched.
    """
    tag = old.tag
    if tag == "_list":
        region = old.props.get("_region")
        if (
            region is None
            or region.cell is None
            or bool(old.props.get("repeat")) != bool(new.props.get("repeat"))
            or old.props.get("keyed", True) is not new.props.get("keyed", True)
        ):
            return False
        region.cell._set(new.props["source"])
        new.props["_region"] = region
    else:
        cell = old.props.get("_cell")
        if cell is None or old.props["select"] is not new.props["select"]:
            return False
        cell._set(new.props["inputs"])
        new.props["_cell"] = cell
    new.el = old.el
    new._frag_end = old._frag_end
    new.scope = old.scope
    new.render_effect = old.render_effect
    new.children = old.children
    new.ns = old.ns
    region = new.props.get("_region")
    if region is not None:
        region.vnode = new
    return True
