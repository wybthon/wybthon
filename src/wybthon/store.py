"""Reactive stores: nested state you read like plain data and edit through drafts.

A store wraps a dict, a list, or a dataclass instance. Reading it in a
tracking scope subscribes to exactly the fields read. A setter opens a
scoped mutable draft; its edits are staged together and become visible at
the next flush, or are all discarded if the callback raises.

Containers are wrapped lazily: creating a store is constant time, and a
nested dict, list, or dataclass gets its reactive bookkeeping the first
time something reads it. Every container is copied on its first edit in a
setter, so a version that a pending transition still shows stays intact.
"""

from __future__ import annotations

import copy
import inspect
from bisect import bisect_left, insort
from collections import deque
from collections.abc import Callable, Iterable, Iterator, Mapping, MutableMapping, MutableSequence, Sequence
from dataclasses import dataclass, fields
from functools import cached_property
from typing import Any, overload
from weakref import ReferenceType, WeakKeyDictionary, ref

from . import _warnings
from .reactivity import _core
from .reactivity._actions import _register_optimistic_revert
from .reactivity._core import Signal, WriteInScopeError, untrack

__all__ = [
    "Store",
    "StoreList",
    "StoreObject",
    "StoreSetter",
    "DraftExpiredError",
    "create_store",
    "create_projection",
    "create_optimistic_store",
    "reconcile",
    "snapshot",
    "deep",
]

_ABSENT: Any = object()
_RAISE: Any = object()
_ATOMIC_TYPES = frozenset({str, int, float, bool, bytes, complex, type(None)})

# Container kinds.
_DICT = 0
_LIST = 1
_OBJECT = 2


class DraftExpiredError(RuntimeError):
    """A draft was used after its setter or deriving function finished."""


@dataclass(frozen=True, slots=True)
class ListChange:
    """Internal sequence edit. Indices refer to the state before this edit."""

    kind: str
    index: int = 0
    removed: tuple[Any, ...] = ()
    added: tuple[Any, ...] = ()


class _Items(list[Any]):
    """One version of a store list's items, numbered for `For`'s edit journal."""

    __slots__ = ("revision",)
    revision: int


def _items(values: Iterable[Any], revision: int = 0) -> _Items:
    items = _Items(values)
    items.revision = revision
    return items


_FIELDS: dict[type, frozenset[str]] = {}


def _fields(cls: type) -> frozenset[str]:
    names = _FIELDS.get(cls)
    if names is None:
        names = _FIELDS[cls] = frozenset(f.name for f in fields(cls))
    return names


def _is_dataclass_instance(value: Any) -> bool:
    return hasattr(type(value), "__dataclass_fields__") and not isinstance(value, type)


class _Root:
    __slots__ = (
        "optimistic",
        "optimistic_signal",
        "derivation",
        "authoritative",
        "authoritative_version",
        "tracks_subtrees",
        "shallow",
    )

    def __init__(self, shallow: bool = False) -> None:
        self.optimistic = False
        self.optimistic_signal: Signal[bool] | None = None
        self.tracks_subtrees = False
        self.authoritative: dict[_Node, Any] | None = None
        self.authoritative_version: Signal[int] = Signal(0)
        self.derivation: _core.Computation | None = None
        self.shallow = shallow

    def ready(self) -> None:
        if _core._authoritative_depth:
            self.authoritative_version()
        comp = self.derivation
        if comp is not None:
            comp._update_if_necessary()
            # Ready reads depend on their properties. Reads of an async or
            # failed derivation also subscribe to its readiness, and
            # pending/error reads to the producer, so that an eventual
            # landing retries them. A settled synchronous derivation has
            # nothing to report.
            if comp._async is not None or comp._error is not None:
                comp._track_readiness()
            if comp._error is not None or (comp._async is not None and comp._async.inflight):
                comp._read()
            elif comp._async is not None or _core._in_action is not None or _core._slow_reads:
                # A settled synchronous derivation has nothing to surface;
                # otherwise the read joins actions and held versions.
                untrack(comp._read)
        if _core._probe_depth and self.optimistic_signal is not None and self.optimistic_signal():
            _core._probe_mark()


def _lookup(data: Any, key: Any) -> Any:
    try:
        return data[key]
    except KeyError, IndexError, TypeError:
        return _ABSENT


def _same(a: Any, b: Any) -> bool:
    """Equality as signals compare it: identity, then `==` (a raising `==` differs)."""
    if a is b:
        return True
    try:
        return bool(b == a)
    except Exception:
        return False


def _release_property() -> None:
    """Marker callback; `_PropertySignal._check_unobserved` does the release."""


class _PropertySignal(Signal[Any]):
    """A store field subscription, released when its last observer leaves.

    Stores keyed by unbounded identifiers (a projection of selected row
    ids, say) would otherwise retain one subscription per key ever read.
    A released field is recreated from the container's state on the next
    tracked read, including staged and held values.
    """

    __slots__ = ("_node", "_key")

    # Constant `Signal` fields, as class attributes: a store creates one of
    # these per field read in a tracking scope.
    _equals = _core._DEFAULT_EQUALS
    _unobserved = staticmethod(_release_property)
    _name = None

    def __init__(self, node: _Node, key: Any, value: Any) -> None:
        self._value = value
        self._pending = None
        self._staged = False
        self._origin = _core._O_NORMAL
        self._write_tx = None
        self._version_source = node
        self._observers = None
        self._node = node
        self._key = key

    def _ride(self, value: Any, origin: int, tx: _core.Transition | None) -> None:
        """Commit `value` along with the container's own commit.

        A setter stages its containers, not each field it changed: the
        container's commit publishes its changed fields with the same
        origin and transition, as their own staged writes would have.
        """
        if self._staged:
            self._pending = value
            self._write_tx = _core._join(self._write_tx, tx)
            if origin > self._origin:
                self._origin = origin
            return
        old = self._value
        if old is value:
            return
        try:
            if value == old:
                return
        except Exception:
            pass
        self._value = value
        if _core._track:
            _core._record(self, old, origin, tx)
        obs = self._observers
        if obs is not None:
            if type(obs) is dict:
                for o in list(obs):
                    o._stale(_core._DIRTY)
            else:
                obs._stale(_core._DIRTY)

    def _check_unobserved(self) -> None:
        if self._observers or self._staged or self in _core._held:
            return
        node = self._node
        key = self._key
        properties = node.properties
        if properties is None or properties.get(key) is not self:
            return
        del properties[key]
        ext = node.ext
        indices = ext.indices if ext is not None else None
        if indices is not None:
            slot = bisect_left(indices, key)
            if slot < len(indices) and indices[slot] == key:
                del indices[slot]


class _NodeExt:
    """A container's rarely needed bookkeeping, allocated on first use."""

    __slots__ = ("indices", "membership", "length", "keys", "version", "pending", "parents", "history")

    def __init__(self) -> None:
        self.indices: list[int] | None = None
        self.membership: dict[Any, Signal[bool]] | None = None
        self.length: Signal[int] | None = None
        self.keys: Signal[int] | None = None
        self.version: Signal[int] | None = None
        self.pending: Signal[int] | None = None
        self.parents: WeakKeyDictionary[_Node, int] | None = None
        self.history: deque[tuple[int, tuple[ListChange, ...]]] | None = None


class _Node(Signal[Any]):
    """One store container (a dict, a list, or a dataclass instance).

    The node is the signal of its container's whole version: its committed
    value is the container's current data, a setter stages a new copy, and
    the reactive core holds the previous copy while a transition keeps it
    on screen. Fields are separate `_PropertySignal`s, caused by the node,
    created when something reads them.

    A node starts as a shell around the raw data it was given. The first
    read copies that data into the node's own container, wrapping nested
    containers in shells of their own, so creating a store, or writing a
    large replacement into one, does work only for what's actually read.
    """

    __slots__ = (
        "raw",
        "kind",
        "cls",
        "properties",
        "pending_keys",
        "root",
        "proxy",
        "_parent",
        "_parent_count",
        "ext",
        "__weakref__",
    )

    # Constant `Signal` fields, as class attributes. A node always stages a
    # new container, so it compares by identity alone.
    _equals = False
    _unobserved = None
    _name = None
    _version_source = None

    def __init__(self, raw: Any, root: _Root, kind: int, cls: type | None, parent: ReferenceType[_Node] | None) -> None:
        self._value = None
        self._pending = None
        self._staged = False
        self._origin = _core._O_NORMAL
        self._write_tx = None
        self._observers = None
        self.raw = raw
        self.kind = kind
        self.cls = cls
        self.properties: dict[Any, _PropertySignal] | None = None
        # Fields whose subscriptions this container's staged version changes.
        self.pending_keys: set[Any] | None = None
        self.root = root
        self.proxy: Any = None
        self._parent = parent
        self._parent_count = 1 if parent is not None else 0
        self.ext: _NodeExt | None = None

    def __repr__(self) -> str:
        kind = ("dict", "list", getattr(self.cls, "__name__", "object"))[self.kind]
        return f"<store {kind} node{' (unread)' if self._value is None else ''}>"

    def _commit(self) -> None:
        if not self._staged:
            return
        keys, self.pending_keys = self.pending_keys, None
        origin, tx = self._origin, self._write_tx
        Signal._commit(self)
        properties = self.properties
        if keys and properties:
            data = self._value
            for key in keys:
                sig = properties.get(key)
                if sig is not None:
                    sig._ride(_lookup(data, key), origin, tx)

    def _commit_now(self, value: Any, origin: int = _core._O_NORMAL) -> None:
        keys, self.pending_keys = self.pending_keys, None
        Signal._commit_now(self, value, origin)
        properties = self.properties
        if keys and properties:
            for key in keys:
                sig = properties.get(key)
                if sig is not None:
                    sig._commit_now(_lookup(value, key), origin)

    def _stage_keys(self, keys: Iterable[Any]) -> None:
        pending = self.pending_keys
        if pending is None:
            self.pending_keys = set(keys)
        else:
            pending.update(keys)

    def _x(self) -> _NodeExt:
        ext = self.ext
        if ext is None:
            ext = self.ext = _NodeExt()
        return ext

    # -- data -------------------------------------------------------------------

    def _encode(self) -> Any:
        """Copy the raw data into this node's own container (first read only)."""
        raw, self.raw = self.raw, None
        root = self.root
        shallow = root.shallow
        # Children share one callback-free weak reference to their parent: a
        # row a component keeps doesn't keep the list it came from.
        parent = ref(self)
        data: Any
        if self.kind == _LIST:
            data = _items(raw if shallow else [_child(v, root, self, parent) for v in raw])
        elif self.kind == _DICT:
            if shallow:
                data = dict(raw)
            else:
                data = {}
                for k, v in raw.items():
                    data[k] = v if type(v) in _ATOMIC_TYPES else _child(v, root, self, parent)
        else:
            data = {}
            for name in _fields(type(raw)):
                v = getattr(raw, name, _ABSENT)
                if v is not _ABSENT:
                    data[name] = v if shallow or type(v) in _ATOMIC_TYPES else _child(v, root, self, parent)
        self._value = data
        authoritative = root.authoritative
        if authoritative is not None and self not in authoritative:
            # Optimistic edits copy before writing, so a container first read
            # now still holds its authoritative version.
            authoritative[self] = data
        return data

    def committed(self) -> Any:
        data = self._value
        return data if data is not None else self._encode()

    def latest(self) -> Any:
        if self._staged:
            return self._pending
        data = self._value
        return data if data is not None else self._encode()

    def visible(self) -> Any:
        if self._value is None:
            self._encode()
        if _core._authoritative_depth and self.root.authoritative is not None:
            return self.root.authoritative.get(self, self.peek())
        return self.peek()

    def held(self) -> Any:
        return _core._held.get(self, _ABSENT)

    # -- structural subscriptions ---------------------------------------------

    @property
    def length(self) -> Signal[int]:
        ext = self._x()
        if ext.length is None:
            sig = ext.length = Signal(len(self.committed()))
            sig._version_source = self
            if self._staged:
                sig._set(len(self._pending))
            held = self.held()
            if held is not _ABSENT and len(held) != sig._value:
                _core._hold(sig, len(held), _core._node_tx[self])
        return ext.length

    def member(self, key: Any) -> Signal[bool]:
        ext = self._x()
        membership = ext.membership
        if membership is None:
            membership = ext.membership = {}
        sig = membership.get(key)
        if sig is None:
            sig = membership[key] = Signal(key in self.committed())
            sig._version_source = self
            if self._staged:
                sig._set(key in self._pending)
            held = self.held()
            if held is not _ABSENT and (key in held) != sig._value:
                _core._hold(sig, key in held, _core._node_tx[self])
        return sig

    @property
    def keys(self) -> Signal[int]:
        ext = self._x()
        if ext.keys is None:
            sig = ext.keys = Signal(0)
            sig._version_source = self
            current = self.committed()
            if self._staged and _structure_changed(current, self._pending):
                sig._set(1)
            held = self.held()
            if held is not _ABSENT and _structure_changed(held, current):
                _core._hold(sig, -1, _core._node_tx[self])
        return ext.keys

    @property
    def version(self) -> Signal[int]:
        ext = self._x()
        if ext.version is None:
            sig = ext.version = Signal(0)
            sig._version_source = self
            self.root.tracks_subtrees = True
            # A first deep subscriber can appear after the setter but before
            # flush. It reads committed data and must see those staged edits
            # when they land, including edits made below this container.
            if _core._staged and self._has_unrevealed(set(), held=False):
                sig._set(1)
            if _core._held and self._has_unrevealed(set(), held=True):
                tx = self._held_transition(set())
                if tx is not None:
                    _core._hold(sig, -1, tx)
        return ext.version

    def _children(self) -> Iterable[Any]:
        data = self._value
        if data is None:
            # A shell's descendants haven't been read, so none is staged or held.
            return ()
        return data.values() if self.kind != _LIST else data

    def _held_transition(self, seen: set[_Node]) -> _core.Transition | None:
        if self in seen:
            return None
        seen.add(self)
        tx = _core._node_tx.get(self)
        for child in self._children():
            if type(child) is _Node:
                tx = _core._join(tx, child._held_transition(seen))
        return tx

    def _has_unrevealed(self, seen: set[_Node], held: bool) -> bool:
        if (self in _core._held) if held else self._staged:
            return True
        if self in seen:
            return False
        seen.add(self)
        return any(type(child) is _Node and child._has_unrevealed(seen, held) for child in self._children())

    def _probe_pending(self) -> None:
        queue = [self]
        seen = set()
        while queue:
            node = queue.pop()
            if node in seen:
                continue
            seen.add(node)
            ext = node._x()
            if ext.pending is None:
                ext.pending = Signal(0)
            ext.pending()
            if _core._probe_touch(node):
                _core._probe_mark()
            if ext.parents is not None:
                queue.extend(ext.parents)
            elif node._parent is not None:
                parent = node._parent()
                if parent is not None:
                    queue.append(parent)

    def _notify_affected(self) -> None:
        """`affects()` marked this subtree: rerun its pending probes."""
        ext = self.ext
        if ext is not None and ext.pending is not None:
            ext.pending._notify()

    # -- parents ------------------------------------------------------------------

    def _link(self, value: Any, amount: int) -> None:
        if type(value) is not _Node:
            return
        ext = value.ext
        parents = ext.parents if ext is not None else None
        if parents is None:
            parent = value._parent() if value._parent is not None else None
            if parent is None:
                if amount > 0:
                    value._parent = ref(self)
                    value._parent_count = amount
                return
            if parent is self:
                value._parent_count += amount
                if value._parent_count <= 0:
                    value._parent = None
                    value._parent_count = 0
                return
            if amount < 0:
                return
            parents = value._x().parents = WeakKeyDictionary({parent: value._parent_count})
            value._parent = None
            value._parent_count = 0
        count = parents.get(self, 0) + amount
        if count > 0:
            parents[self] = count
        else:
            parents.pop(self, None)

    # -- reads --------------------------------------------------------------------

    def _property(self, key: Any) -> _PropertySignal:
        properties = self.properties
        if properties is None:
            properties = self.properties = {}
        data = self._value
        sig = properties[key] = _PropertySignal(self, key, _lookup(data, key))
        if self.kind == _LIST:
            ext = self._x()
            if ext.indices is None:
                ext.indices = [key]
            else:
                insort(ext.indices, key)
        if self._staged:
            self._stage_keys((key,))
        held = _core._held.get(self, _ABSENT)
        if held is not _ABSENT:
            shown = _lookup(held, key)
            if not _same(shown, sig._value):
                _core._hold(sig, shown, _core._node_tx[self])
        return sig

    def read(self, key: Any, default: Any = _RAISE) -> Any:
        observer = _core._current_observer
        if observer is _core._PROBE_OBSERVER:
            # A store field is reactive: a binding's static probe ends here,
            # before doing the read it would repeat.
            raise _core._Escape
        if self._value is None:
            self._encode()
        comp = self.root.derivation
        if _core._authoritative_depth or _core._probe_depth:
            self.root.ready()
            if _core._probe_depth:
                self._probe_pending()
        elif comp is not None and (
            comp._state != _core._CLEAN
            or comp._async is not None
            or comp._error is not None
            or _core._in_action is not None
            or _core._slow_reads
        ):
            # A derived store whose derivation is settled, synchronous, and
            # not failing has nothing to bring up to date or to surface.
            self.root.ready()
        if observer is not None or _core._probe_depth:
            properties = self.properties
            sig = properties.get(key) if properties is not None else None
            if sig is None:
                sig = self._property(key)
            value = sig()
            if not _core._slow_reads and not _core._authoritative_depth and _core._in_action is None:
                if value is _ABSENT:
                    return self._missing(key, default)
                return value if type(value) is not _Node else _wrap(value)
        # The container's revealed version also covers properties that weren't
        # observed before a transition began, and an action's own staged
        # edits. Read history can't change visibility.
        value = _lookup(self.visible(), key)
        if value is _ABSENT:
            return self._missing(key, default)
        return value if type(value) is not _Node else _wrap(value)

    def _missing(self, key: Any, default: Any) -> Any:
        if default is not _RAISE:
            return default
        if self.kind == _LIST:
            raise IndexError("list index out of range")
        if self.kind == _OBJECT:
            raise AttributeError(key)
        raise KeyError(key)

    # -- writes -------------------------------------------------------------------

    def publish(self, data: Any, changes: Sequence[ListChange], touched: Iterable[Any]) -> bool:
        """Stage a setter's finished copy of this container (False when unchanged)."""
        old_data = self.latest()
        ext = self.ext
        if self.kind != _LIST:
            changed = []
            structural = False
            get_old, get_new = old_data.get, data.get
            for k in touched:
                before, after = get_old(k, _ABSENT), get_new(k, _ABSENT)
                if before is after or _same(before, after):
                    continue
                changed.append(k)
                if before is _ABSENT or after is _ABSENT:
                    structural = True
                if type(before) is _Node:
                    self._link(before, -1)
                if type(after) is _Node:
                    self._link(after, 1)
            if not changed:
                return False
            self._set(data)
        else:
            if not changes:
                return False
            structural = len(old_data) != len(data)
            changed_set: set[Any] = set()
            reset = False
            indices = ext.indices if ext is not None else None
            for change in changes:
                if change.kind == "reset":
                    reset = True
                    break
                for value in change.removed:
                    self._link(value, -1)
                for value in change.added:
                    self._link(value, 1)
                if change.kind == "set":
                    changed_set.add(change.index)
                elif indices:
                    end = change.index + max(len(change.removed), len(change.added))
                    shifted = len(change.removed) != len(change.added)
                    start_slot = bisect_left(indices, change.index)
                    end_slot = len(indices) if shifted else bisect_left(indices, end)
                    changed_set.update(indices[start_slot:end_slot])
            if reset:
                # General replacement is deliberately the O(n) fallback.
                for value in old_data:
                    self._link(value, -1)
                for value in data:
                    self._link(value, 1)
                if self.properties:
                    changed_set.update(self.properties)
            revision = data.revision = old_data.revision + 1
            self._set(data)
            ext = self._x()
            if ext.history is None:
                ext.history = deque(maxlen=64)
            ext.history.append((revision, tuple(changes)))
            changed = changed_set  # type: ignore[assignment]
        if ext is not None:
            if structural and ext.keys is not None:
                ext.keys._set(ext.keys._latest() + 1)
            if ext.length is not None:
                ext.length._set(len(data))
        properties = self.properties
        if properties:
            if self._staged:
                self._stage_keys(changed)
            else:
                # Committed at once (an eager derivation's write).
                for key in changed:
                    sig = properties.get(key)
                    if sig is not None:
                        sig._set(_lookup(data, key))
        membership = ext.membership if ext is not None else None
        if membership:
            for key in changed:
                member = membership.get(key)
                if member is not None:
                    member._set(key in data)
        return True

    def bump(self, seen: set[_Node]) -> None:
        if self in seen:
            return
        seen.add(self)
        ext = self.ext
        if ext is not None:
            if ext.version is not None:
                ext.version._set(ext.version._latest() + 1)
            if ext.parents is not None:
                for parent in tuple(ext.parents):
                    parent.bump(seen)
                return
        if self._parent is not None:
            parent = self._parent()
            if parent is not None:
                parent.bump(seen)


def _structure_changed(before: Any, after: Any) -> bool:
    if isinstance(before, dict):
        return bool(before.keys() != after.keys())
    return len(before) != len(after)


def _kind(value: Any) -> tuple[int, type | None] | None:
    t = type(value)
    if t is dict:
        return _DICT, None
    if t is list:
        return _LIST, None
    if hasattr(t, "__dataclass_fields__") and not isinstance(value, type):
        return _OBJECT, t
    if isinstance(value, Mapping):
        return _DICT, None
    if isinstance(value, list):
        return _LIST, None
    # Tuples (and named tuples) are immutable values, stored as they are.
    return None


def _child(value: Any, root: _Root, owner: _Node, parent: ReferenceType[_Node]) -> Any:
    """The stored form of a value placed in a container: an atom, a node, or a copy."""
    if type(value) in _ATOMIC_TYPES:
        return value
    if type(value) is _Node:
        if value.root is root:
            owner._link(value, 1)
            return value
        value = _snapshot(value, False, {}, None)
    elif isinstance(value, _Proxy):
        node = value._node
        if node.root is root:
            owner._link(node, 1)
            return node
        value = snapshot(value)
    kind = _kind(value)
    if kind is None:
        return copy.deepcopy(value)
    if kind[0] == _DICT and type(value) is not dict:
        value = dict(value)
    return _Node(value, root, kind[0], kind[1], parent)


def _stored(value: Any, root: _Root) -> Any:
    """A value written by a draft; parents are linked when its setter commits."""
    if type(value) in _ATOMIC_TYPES:
        return value
    if type(value) is _Node:
        # An entity reconcile matched (or moved) within this store.
        return value if value.root is root else _snapshot(value, False, {}, None)
    if root.shallow:
        if isinstance(value, _Proxy):
            return snapshot(value)
        return value
    if isinstance(value, _Proxy):
        value._check()
        node = value._node
        if node.root is root:
            return node
        value = snapshot(value)
    kind = _kind(value)
    if kind is None:
        return copy.deepcopy(value)
    if kind[0] == _DICT and type(value) is not dict:
        value = dict(value)
    return _Node(value, root, kind[0], kind[1], None)


def _root_node(initial: Any, shallow: bool = False) -> _Node:
    if isinstance(initial, _Proxy):
        initial = snapshot(initial)
    kind = _kind(initial)
    if kind is None:
        raise TypeError(
            "A store root must be a dict, a list, or a dataclass instance; use create_signal for scalar state"
        )
    if kind[0] == _DICT and type(initial) is not dict:
        initial = dict(initial)
    return _Node(initial, _Root(shallow), kind[0], kind[1], None)


def _wrap(value: Any) -> Any:
    if type(value) is not _Node:
        return value
    proxy = value.proxy
    if proxy is None:
        proxy = value.proxy = _new_proxy(_PROXIES[value.kind])
        _set_proxy_node(proxy, value)
        _set_proxy_session(proxy, None)
    return proxy


def _wrap_draft(value: Any, session: _Session) -> Any:
    if type(value) is not _Node:
        return value
    proxies = session.proxies
    proxy = proxies.get(value)
    if proxy is None:
        # A draft proxy per container per setter: built without `__init__`.
        proxy = proxies[value] = _new_proxy(_DRAFTS[value.kind])
        _set_proxy_node(proxy, value)
        _set_proxy_session(proxy, session)
    return proxy


class _Session:
    """One setter's (or deriving function's) drafts and edits."""

    __slots__ = ("active", "work", "changes", "touched", "proxies")

    def __init__(self) -> None:
        self.active = True
        self.work: dict[_Node, Any] = {}
        self.changes: dict[_Node, list[ListChange]] = {}
        self.touched: dict[_Node, set[Any]] = {}
        self.proxies: dict[_Node, Any] = {}

    def check(self) -> None:
        if not self.active:
            raise DraftExpiredError("Drafts are valid only while their setter or deriving function runs")

    def close(self) -> None:
        self.active = False
        self.proxies.clear()

    def data(self, node: _Node) -> Any:
        if not self.active:
            self.check()
        data = self.work.get(node)
        if data is None:
            data = node.latest()
        return data

    def own(self, node: _Node) -> Any:
        """This session's private copy of `node`'s data, made on its first edit."""
        data = self.work.get(node)
        if data is None:
            base = node.latest()
            data = self.work[node] = dict(base) if node.kind != _LIST else _items(base, base.revision)
        return data

    def write(self, node: _Node, key: Any, value: Any) -> None:
        if not self.active:
            self.check()
        work = self.work
        data = work.get(node)
        owned = data is not None
        if not owned:
            data = node.latest()
        if type(value) not in _ATOMIC_TYPES:
            value = _stored(value, node.root)
        if node.kind == _LIST:
            n = len(data)
            if key < 0:
                key += n
            if not 0 <= key < n:
                raise IndexError("list assignment index out of range")
            old = data[key]
            if _same(old, value):
                return
            self.own(node)[key] = value
            self.changes.setdefault(node, []).append(ListChange("set", key, (old,), (value,)))
            return
        if _same(data.get(key, _ABSENT), value):
            return
        if not owned:
            data = work[node] = dict(data)
        data[key] = value
        touched = self.touched.get(node)
        if touched is None:
            self.touched[node] = {key}
        else:
            touched.add(key)

    def delete_key(self, node: _Node, key: Any) -> None:
        data = self.data(node)
        if key not in data:
            raise KeyError(key)
        del self.own(node)[key]
        self.touched.setdefault(node, set()).add(key)

    def splice(self, node: _Node, start: int, delete: int, values: Iterable[Any], *, kind: str = "splice") -> None:
        data = self.data(node)
        root = node.root
        added = tuple(_stored(v, root) for v in values)
        removed = tuple(data[start : start + delete])
        if not removed and not added:
            return
        self.own(node)[start : start + delete] = added
        self.changes.setdefault(node, []).append(ListChange(kind, start, removed, added))

    def replace_list(self, node: _Node, values: Iterable[Any]) -> None:
        self.check()
        root = node.root
        self.work[node] = _items(_stored(v, root) for v in values)
        self.changes[node] = [ListChange("reset")]

    def commit(self) -> None:
        bumped: set[_Node] = set()
        for node, data in self.work.items():
            if node.publish(data, self.changes.get(node, ()), self.touched.get(node, ())) and node.root.tracks_subtrees:
                node.bump(bumped)
        self.close()


class _Proxy:
    __slots__ = ("_node", "_session")
    _node: _Node
    _session: _Session | None

    def __init__(self, node: _Node, session: _Session | None = None) -> None:
        object.__setattr__(self, "_node", node)
        object.__setattr__(self, "_session", session)

    def _check(self) -> None:
        if self._session is not None:
            self._session.check()

    def _data(self) -> Any:
        session = self._session
        if session is not None:
            return session.data(self._node)
        node = self._node
        node.root.ready()
        if _core._probe_depth:
            node._probe_pending()
        return node.visible()

    def _read(self, key: Any, default: Any = _RAISE) -> Any:
        session = self._session
        if session is not None:
            value = _lookup(session.data(self._node), key)
            if value is _ABSENT:
                return self._node._missing(key, default)
            return value if type(value) is not _Node else _wrap_draft(value, session)
        return self._node.read(key, default)

    def _wyb_affect_node(self) -> Any:
        return self._node

    def _wyb_refresh(self) -> Any:
        comp = self._node.root.derivation
        if comp is None:
            raise TypeError("Only derived stores can be refreshed")
        comp._refresh()
        return comp

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("A store is read-only; edit a draft inside its setter")

    def __eq__(self, other: Any) -> bool:
        return bool(deep(self) == deep(other))

    __hash__ = None

    def __repr__(self) -> str:
        return f"{type(self).__name__}({snapshot(self)!r})"


class Store(_Proxy, Mapping[Any, Any]):
    """The read-only reactive view of a dict store.

    Read it like a dict: `store["key"]`, `store.get("key")`, `in`, `len`,
    and iteration are all tracked. Missing keys raise `KeyError`.
    """

    __slots__ = ()

    def __getitem__(self, key: Any) -> Any:
        if self._session is None:
            return self._node.read(key)
        return self._read(key)

    def get(self, key: Any, default: Any = None) -> Any:
        """Return the value for `key`, or `default` when absent (tracked either way).

        A tracked read of an absent key subscribes to it, so a computation
        reading `store.get(row_id)` re-runs when that key appears.
        """
        if self._session is None:
            return self._node.read(key, default)
        return self._read(key, default)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        raise AttributeError(
            f"{name!r}: read a dict store's keys with store[{name!r}]; use a dataclass for attribute access"
        )

    def __iter__(self) -> Iterator[Any]:
        if self._session is None:
            self._node.keys()
            return iter(self._data())
        return iter(tuple(self._data()))

    def __len__(self) -> int:
        if self._session is not None:
            return len(self._data())
        node = self._node
        node.root.ready()
        if _core._probe_depth:
            node._probe_pending()
        node.length()
        return len(node.visible())

    def __contains__(self, key: object) -> bool:
        if self._session is not None:
            return key in self._data()
        node = self._node
        node.root.ready()
        if _core._probe_depth:
            node._probe_pending()
        node.member(key)()
        return key in node.visible()

    def __repr__(self) -> str:
        return f"Store({snapshot(self)!r})"


class StoreList[T](_Proxy, Sequence[T]):
    """The read-only reactive view of a list store. Entity proxies survive reorders."""

    __slots__ = ()

    @overload
    def __getitem__(self, index: int) -> T: ...

    @overload
    def __getitem__(self, index: slice) -> list[T]: ...

    def __getitem__(self, index: int | slice) -> T | list[T]:
        if type(index) is not int:
            if isinstance(index, slice):
                return [self[i] for i in range(*index.indices(len(self)))]
            if not isinstance(index, int):
                raise TypeError("list indices must be integers or slices")
        session = self._session
        if session is not None:
            value = session.data(self._node)[index]
            return value if type(value) is not _Node else _wrap_draft(value, session)
        if index < 0:
            index += len(self)
            if index < 0:
                raise IndexError("list index out of range")
        return self._node.read(index)

    def __len__(self) -> int:
        if self._session is not None:
            return len(self._data())
        node = self._node
        node.root.ready()
        if _core._probe_depth:
            node._probe_pending()
        node.length()
        return len(node.visible())

    def __iter__(self) -> Iterator[T]:
        for i in range(len(self)):
            yield self[i]

    def __repr__(self) -> str:
        return f"StoreList({snapshot(self)!r})"

    def _wyb_list_state(self) -> _Items:
        node = self._node
        node.root.ready()
        if _core._probe_depth:
            node._probe_pending()
        if node._value is None:
            node._encode()
        return node()

    def _wyb_changes_since(self, revision: int) -> tuple[ListChange, ...] | None:
        node = self._node
        current = node.visible().revision
        if current == revision:
            return ()
        ext = node.ext
        history = ext.history if ext is not None else None
        records = [(r, changes) for r, changes in history or () if revision < r <= current]
        if not records or records[0][0] != revision + 1 or records[-1][0] != current:
            return None
        return tuple(change for _, changes in records for change in changes)


def _class_attribute(cls: type, name: str) -> Any:
    for klass in cls.__mro__:
        attrs = klass.__dict__
        if name in attrs:
            return attrs[name]
    return _ABSENT


class StoreObject(_Proxy):
    """The read-only reactive view of a dataclass store.

    Fields read as tracked attributes. Methods and properties of the
    dataclass work too, reading through the view, and `isinstance` sees
    the dataclass, so a store typed as your class behaves like one.
    """

    __slots__ = ()

    @property  # type: ignore[misc]
    def __class__(self) -> type:
        return self._node.cls

    def __getattr__(self, name: str) -> Any:
        node = self._node
        cls = node.cls
        assert cls is not None
        if name in _fields(cls):
            return self._read(name)
        attr = _class_attribute(cls, name)
        if attr is _ABSENT:
            raise AttributeError(f"{cls.__name__!r} store has no attribute {name!r}")
        if isinstance(attr, cached_property):
            # The view has no instance dict to cache in, and a cached value
            # would go stale: compute it on each read, tracking what it reads.
            return attr.func(self)
        get = getattr(type(attr), "__get__", None)
        return get(attr, self, cls) if get is not None else attr

    def __dir__(self) -> list[str]:
        cls = self._node.cls
        return sorted(set(dir(cls)) | set(_fields(cls)))

    def __repr__(self) -> str:
        return f"Store({snapshot(self)!r})"


class _Draft(Store, MutableMapping[Any, Any]):
    """A dict draft that expires when its callback returns."""

    __slots__ = ()

    def __setitem__(self, key: Any, value: Any) -> None:
        session = self._session
        assert session is not None
        session.write(self._node, key, value)

    def __delitem__(self, key: Any) -> None:
        session = self._session
        assert session is not None
        session.delete_key(self._node, key)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError(f"Write a dict draft's keys with draft[{name!r}] = ...; use a dataclass for attributes")


class _DraftList[T](StoreList[T], MutableSequence[T]):
    """A list draft with Python's list mutation methods."""

    __slots__ = ()

    @overload
    def __setitem__(self, index: int, value: T) -> None: ...

    @overload
    def __setitem__(self, index: slice, value: Iterable[T]) -> None: ...

    def __setitem__(self, index: int | slice, value: Any) -> None:
        session = self._session
        assert session is not None
        if isinstance(index, slice):
            start, stop, step = index.indices(len(self))
            values = list(value)
            if step == 1:
                session.splice(self._node, start, max(0, stop - start), values)
            else:
                indices = range(start, stop, step)
                if len(indices) != len(values):
                    raise ValueError("attempt to assign sequence of different size to extended slice")
                for i, v in zip(indices, values, strict=True):
                    session.write(self._node, i, v)
        else:
            session.write(self._node, index, value)

    def __delitem__(self, index: int | slice) -> None:
        session = self._session
        assert session is not None
        n = len(self._data())
        if isinstance(index, slice):
            start, stop, step = index.indices(n)
            if step == 1:
                session.splice(self._node, start, max(0, stop - start), ())
            else:
                for i in sorted(range(start, stop, step), reverse=True):
                    session.splice(self._node, i, 1, ())
        else:
            if index < 0:
                index += n
            if not 0 <= index < n:
                raise IndexError("list assignment index out of range")
            session.splice(self._node, index, 1, ())

    def insert(self, index: int, value: T) -> None:
        """Insert a value at a draft index."""
        session = self._session
        assert session is not None
        n = len(self)
        index = max(0, n + index) if index < 0 else min(index, n)
        session.splice(self._node, index, 0, (value,))

    def append(self, value: T) -> None:
        """Append a value."""
        session = self._session
        assert session is not None
        session.splice(self._node, len(self), 0, (value,))

    def extend(self, values: Iterable[T]) -> None:
        """Append values in one recorded splice."""
        session = self._session
        assert session is not None
        session.splice(self._node, len(self), 0, tuple(values))

    def clear(self) -> None:
        """Remove all items in one edit."""
        session = self._session
        assert session is not None
        session.splice(self._node, 0, len(self), (), kind="clear")

    def sort(self, *, key: Callable[[T], Any] | None = None, reverse: bool = False) -> None:
        """Sort entities without changing their identities."""
        session = self._session
        assert session is not None
        session.replace_list(self._node, sorted(self, key=key, reverse=reverse))

    def reverse(self) -> None:
        """Reverse entity order in the draft."""
        session = self._session
        assert session is not None
        session.replace_list(self._node, reversed(self))

    def move(self, start: int, target: int, count: int = 1) -> None:
        """Move a contiguous range to a final index, preserving its entities."""
        n = len(self)
        if count < 0 or start < 0 or start + count > n or not 0 <= target <= n - count:
            raise IndexError("invalid list move range")
        if not count or start == target:
            return
        items = self[start : start + count]
        del self[start : start + count]
        self[target:target] = items


class _DraftObject(StoreObject):
    """A dataclass draft: assign fields as attributes."""

    __slots__ = ()

    def __setattr__(self, name: str, value: Any) -> None:
        session = self._session
        assert session is not None
        node = self._node
        cls = node.cls
        assert cls is not None
        if name in _fields(cls):
            session.write(node, name, value)
            return
        attr = _class_attribute(cls, name)
        setter = getattr(type(attr), "__set__", None)
        if setter is None:
            raise AttributeError(f"{cls.__name__!r} has no field {name!r}")
        setter(attr, self, value)

    def __delattr__(self, name: str) -> None:
        raise AttributeError(f"Can't delete field {name!r} of a dataclass store")


_PROXIES: tuple[Any, ...] = (Store, StoreList, StoreObject)
_new_proxy = object.__new__
_set_proxy_node = _Proxy.__dict__["_node"].__set__
_set_proxy_session = _Proxy.__dict__["_session"].__set__
_DRAFTS: tuple[Any, ...] = (_Draft, _DraftList, _DraftObject)


def _identity(session: _Session, item: _Node, key: str | Callable[[Any], Any]) -> Any:
    if callable(key):
        return key(_wrap_draft(item, session))
    return _lookup(session.data(item), key)


def _replacement_fields(node: _Node, data: Any) -> Mapping[Any, Any] | None:
    """`data`'s fields when it can replace `node`'s container in place, else None."""
    if node.kind == _DICT:
        return data if isinstance(data, Mapping) else None
    if node.kind == _OBJECT:
        if isinstance(data, Mapping):
            return data
        if type(data) is node.cls:
            return {name: getattr(data, name) for name in _fields(type(data)) if hasattr(data, name)}
    return None


def _merge(session: _Session, node: _Node, data: Any, key: str | Callable[[Any], Any] | None) -> None:
    if isinstance(data, _Proxy):
        data = snapshot(data)
    current = session.data(node)
    replacement = _replacement_fields(node, data)
    if replacement is not None:
        if node.kind == _DICT:
            for k in tuple(current):
                if k not in replacement:
                    session.delete_key(node, k)
        names = _fields(node.cls) if node.kind == _OBJECT else None
        for k, value in replacement.items():
            if names is not None and k not in names:
                raise AttributeError(f"{node.cls.__name__!r} has no field {k!r}")
            old = _lookup(session.data(node), k)
            if type(old) is _Node and _compatible(old, value):
                _merge(session, old, value, key)
            else:
                session.write(node, k, value)
    elif node.kind == _LIST and isinstance(data, (Sequence, _Items)) and not isinstance(data, (str, bytes)):
        by_key: dict[Any, deque[_Node]] = {}
        if key is not None:
            for item in current:
                if type(item) is _Node and item.kind != _LIST:
                    ident = _identity(session, item, key)
                    if ident is not _ABSENT:
                        by_key.setdefault(ident, deque()).append(item)
        result = []
        for item in data:
            bucket = None
            if key is not None:
                if isinstance(item, Mapping):
                    bucket = by_key.get(key(item) if callable(key) else item.get(key, _ABSENT))
                elif _is_dataclass_instance(item):
                    bucket = by_key.get(key(item) if callable(key) else getattr(item, key, _ABSENT))
            if bucket:
                old = bucket.popleft()
                _merge(session, old, item, key)
                result.append(old)
            else:
                result.append(_stored(item, node.root))
        if len(current) != len(result) or any(not _same(a, b) for a, b in zip(current, result, strict=False)):
            session.replace_list(node, result)
    elif node.kind == _OBJECT and _is_dataclass_instance(data):
        raise TypeError(
            f"A {node.cls.__name__} store can't be replaced with a {type(data).__name__}; replace it from its parent"
        )
    else:
        raise TypeError("A store container's type can't change; replace it from its parent")


def _compatible(node: _Node, data: Any) -> bool:
    if node.kind == _LIST:
        return isinstance(data, (list, tuple, StoreList))
    if node.kind == _OBJECT:
        # Plain mappings (decoded JSON, say) merge into a dataclass's fields.
        if isinstance(data, StoreObject):
            return data._node.cls is node.cls
        return type(data) is node.cls or isinstance(data, Mapping)
    return isinstance(data, Mapping)


def _modify(session: _Session, node: _Node, modifier: Any) -> None:
    if isinstance(modifier, _Reconcile):
        _merge(session, node, modifier.data, modifier.key)
    elif isinstance(modifier, (Mapping, list, tuple, _Proxy)) or _is_dataclass_instance(modifier):
        _merge(session, node, modifier, None)
    elif callable(modifier):
        result = modifier(_wrap_draft(node, session))
        if inspect.isawaitable(result):
            if inspect.iscoroutine(result):
                result.close()
            raise TypeError("Store setters are synchronous; await work in an action before opening a draft")
        if result is not None:
            _merge(session, node, result, None)
    else:
        raise TypeError("A store setter expects a draft callback, reconcile result, or replacement data")


class StoreSetter[T]:
    """Apply an atomic draft edit. Exceptions discard all changes from the call."""

    __slots__ = ("_node",)

    def __init__(self, node: _Node) -> None:
        self._node = node

    def __call__(self, modifier: Callable[[T], object] | T | _Reconcile[T]) -> None:
        """Stage a synchronous atomic edit or replacement."""
        if _core._current_observer is not None and _warnings.DEV_MODE:
            raise WriteInScopeError(
                "Cannot write a store inside a tracking scope; use an effect's apply stage or an action"
            )
        session = _Session()
        # A setter allocates in a burst (copies of each container it edits)
        # that outlives it, like a flush does: don't let the collector
        # traverse the heap partway through.
        _core._gc_pause()
        try:
            _modify(session, self._node, modifier)
            session.commit()
        finally:
            session.close()
            _core._gc_resume()


@overload
def create_store[T](initial: Callable[[T], object], seed: T, *, shallow: bool = False) -> tuple[T, StoreSetter[T]]: ...


@overload
def create_store(
    initial: Callable[[], object], seed: None = None, *, shallow: bool = False
) -> tuple[Any, StoreSetter[Any]]: ...


@overload
def create_store[T](initial: T, seed: None = None, *, shallow: bool = False) -> tuple[T, StoreSetter[T]]: ...


def create_store(initial: Any, seed: Any = None, *, shallow: bool = False) -> tuple[Any, StoreSetter[Any]]:
    """Create a reactive store and its atomic draft setter.

    `initial` is a dict, a list, or a dataclass instance; the store takes
    ownership of it, so don't keep mutating it yourself. The returned view
    is typed as `initial`'s own type: `create_store(State(...))` gives a
    `State` whose fields are tracked attributes, and the setter takes
    `Callable[[State], object]`.

    With a function, the store is derived: the function either mutates
    the draft it's given or returns new data (reconciled by `"id"`),
    synchronously or asynchronously. Its reads are tracked and its
    writes are staged together. `seed` is the starting data.

    With `shallow=True`, only the top level is reactive: nested values
    are stored and returned as they are, and replacing one is the only
    way to change it.
    """
    if callable(initial) and not _is_dataclass_instance(initial):
        node = _root_node({} if seed is None else seed, shallow)
        _run_projection(node, initial)
    else:
        node = _root_node(initial, shallow)
    return _wrap(node), StoreSetter(node)


def _run_projection(node: _Node, fn: Callable[..., Any]) -> None:
    takes_draft = _core._positional_count(fn) != 0

    def compute() -> Any:
        session = _Session()
        try:
            result = fn(_wrap_draft(node, session)) if takes_draft else fn()
        except BaseException:
            session.close()
            raise
        if inspect.isasyncgen(result):

            async def stream() -> Any:
                emitted = False
                try:
                    async for value in result:
                        if value is not None:
                            _merge(session, node, value, "id")
                        landing = _Session()
                        landing.work, session.work = session.work, {}
                        landing.changes, session.changes = session.changes, {}
                        landing.touched, session.touched = session.touched, {}
                        landing.close()
                        emitted = True
                        yield landing
                    if not emitted:
                        empty = _Session()
                        empty.close()
                        yield empty
                finally:
                    session.close()
                    await result.aclose()

            return stream()
        if inspect.isawaitable(result):

            async def wait() -> Any:
                try:
                    value = await result
                    if value is not None:
                        _merge(session, node, value, "id")
                    return session
                finally:
                    session.close()

            return wait()
        try:
            if result is not None:
                _merge(session, node, result, "id")
            return session
        finally:
            session.close()

    def apply(session: _Session) -> None:
        session.commit()

    comp = _core.Computation(
        compute, kind=_core._K_RENDER, apply_scope=False, apply=apply, pass_prev=False, eager=True, data=True
    )
    if _core._current_owner is not None:
        _core._current_owner._add_child(comp)
    node.root.derivation = comp
    comp._update_if_necessary()


@overload
def create_projection[T](fn: Callable[[T], object], initial: T) -> T: ...


@overload
def create_projection(fn: Callable[[], object], initial: None = None) -> Any: ...


@overload
def create_projection[T](fn: Callable[[], object], initial: T) -> T: ...


def create_projection(fn: Callable[..., Any], initial: Any = None) -> Any:
    """Create a read-only derived store with memo readiness and refresh semantics."""
    node = _root_node({} if initial is None else initial)
    _run_projection(node, fn)
    return _wrap(node)


@overload
def create_optimistic_store[T](
    source: Callable[[], T], initial: Any = None
) -> tuple[T, Callable[[Callable[[T], object] | T], None]]: ...


@overload
def create_optimistic_store[T](
    source: T, initial: None = None
) -> tuple[T, Callable[[Callable[[T], object] | T], None]]: ...


def create_optimistic_store(source: Any, initial: Any = None) -> tuple[Any, Callable[[Any], None]]:
    """Layer optimistic draft edits over a reactive authoritative source.

    Active edits replay in submission order when the source changes. They are
    removed when their submitting action settles; other actions keep their edits. Draft callbacks
    must be deterministic: replay mustn't perform network or other side effects.
    """
    derived = callable(source) and not _is_dataclass_instance(source)
    state: Any = ({} if initial is None else initial) if derived else source
    node = _root_node(state)
    base = [snapshot(state)]
    node.root.optimistic_signal = Signal(False)
    overlays: list[Any] = []
    groups: dict[Any, object] = {}

    def capture_base(session: _Session) -> None:
        captured: dict[_Node, Any] = {}
        queue = [node]
        while queue:
            current = queue.pop()
            if current in captured or (current._value is None and current not in session.work):
                # A shell records its authoritative version when it's first read.
                continue
            data = session.data(current)
            captured[current] = dict(data) if current.kind != _LIST else _items(data, data.revision)
            queue.extend(value for value in (data.values() if current.kind != _LIST else data) if type(value) is _Node)
        node.root.authoritative = captured
        version = node.root.authoritative_version
        version._set(version._latest() + 1, _core._O_REVEAL)

    def rebuild() -> None:
        session = _Session()
        try:
            _merge(session, node, base[0], "id")
            capture_base(session)
            for _, modifier in overlays:
                _modify(session, node, modifier)
            session.commit()
        finally:
            session.close()

    if derived:

        def apply_base(data: Any) -> None:
            base[0] = snapshot(data)
            rebuild()

        def read_base() -> Any:
            value = source()
            if inspect.isawaitable(value):

                async def wait() -> Any:
                    return deep(await value)

                return wait()
            return deep(value)

        comp = _core.Computation(
            read_base, kind=_core._K_RENDER, apply_scope=False, apply=apply_base, pass_prev=False, eager=True, data=True
        )
        if _core._current_owner is not None:
            _core._current_owner._add_child(comp)
        node.root.derivation = comp
        comp._update_if_necessary()

    def set_optimistic(modifier: Any) -> None:
        _core._optimistic_depth += 1
        try:
            if not node.root.optimistic:
                session = _Session()
                try:
                    capture_base(session)
                finally:
                    session.close()
            StoreSetter(node)(modifier)
            group = _core._in_action
            first = group not in groups
            token = groups.setdefault(group, object())
            overlays.append((token, modifier))
            node.root.optimistic = True
            node.root.optimistic_signal._set(True, _core._O_REVEAL)
        finally:
            _core._optimistic_depth -= 1

        if not first:
            return

        def revert() -> None:
            groups.pop(group, None)
            overlays[:] = [edit for edit in overlays if edit[0] is not token]
            node.root.optimistic = bool(overlays)
            node.root.optimistic_signal._set(bool(overlays), _core._O_REVEAL)
            _core._optimistic_depth += 1
            try:
                untrack(rebuild)
            finally:
                _core._optimistic_depth -= 1

        _register_optimistic_revert(revert)

    return _wrap(node), set_optimistic


@dataclass(frozen=True, slots=True)
class _Reconcile[T]:
    data: Any
    key: str | Callable[[Any], Any] | None


def reconcile[T](data: T, key: str | Callable[[Any], Any] | None = "id") -> _Reconcile[T]:
    """Prepare replacement data, preserving matched list entity identities.

    `key` names the field that identifies list entities (`"id"` by
    default), or is a function computing the identity from an entity.
    `key=None` replaces list entities positionally. Duplicate keys are
    matched in occurrence order, without assigning the same entity to
    multiple rows.
    """
    return _Reconcile(snapshot(data), key)


def _blank(cls: Any) -> Any:
    """An instance of a dataclass whose fields the caller sets, without running `__init__`."""
    return object.__new__(cls) if cls.__new__ is object.__new__ else cls.__new__(cls)


def _snapshot_raw(value: Any, memo: dict[int, Any]) -> Any:
    t = type(value)
    if t in _ATOMIC_TYPES:
        return value
    if t is _Node or isinstance(value, _Proxy):
        return _snapshot(value, False, memo, None)
    found = memo.get(id(value))
    if found is not None:
        return found
    kind = _kind(value)
    if kind is None:
        return copy.deepcopy(value)
    result: Any
    if kind[0] == _LIST:
        result = memo[id(value)] = []
        result.extend(_snapshot_raw(v, memo) for v in value)
    elif kind[0] == _DICT:
        result = memo[id(value)] = {}
        result.update((k, _snapshot_raw(v, memo)) for k, v in value.items())
    else:
        result = memo[id(value)] = _blank(t)
        for name in _fields(t):
            if hasattr(value, name):
                object.__setattr__(result, name, _snapshot_raw(getattr(value, name), memo))
    return result


def _snapshot(value: Any, track: bool, memo: dict[int, Any], session: _Session | None) -> Any:
    if type(value) in _ATOMIC_TYPES:
        return value
    if isinstance(value, _Proxy):
        value._check()
        node = value._node
        session = value._session
    elif type(value) is _Node:
        node = value
    else:
        return _snapshot_raw(value, memo)
    found = memo.get(id(node))
    if found is not None:
        return found
    result: Any
    if session is not None:
        data = session.data(node)
    else:
        node.root.ready()
        if _core._probe_depth:
            node._probe_pending()
        if track:
            node.version()
        if node._value is None and not _core._authoritative_depth:
            # Nothing has read this container yet: its raw data is current.
            result = _snapshot_raw(node.raw, memo)
            memo[id(node)] = result
            return result
        data = node.visible()
    if node.kind == _LIST:
        result = memo[id(node)] = []
        result.extend(_snapshot(v, False, memo, session) for v in data)
    elif node.kind == _DICT:
        result = memo[id(node)] = {}
        result.update((k, _snapshot(v, False, memo, session)) for k, v in data.items())
    else:
        cls = node.cls
        assert cls is not None
        result = memo[id(node)] = _blank(cls)
        for name, v in data.items():
            object.__setattr__(result, name, _snapshot(v, False, memo, session))
    return result


def snapshot[T](value: T) -> T:
    """Return a detached, untracked copy of the currently visible state."""
    return untrack(lambda: _snapshot(value, False, {}, None))


def deep[T](value: T) -> T:
    """Return a detached snapshot, tracking changes only within this subtree."""
    return _snapshot(value, True, {}, None)


def _register() -> None:
    from . import _regions

    _regions.register_store(StoreList, _wrap)


_register()
