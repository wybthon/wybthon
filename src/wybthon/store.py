"""Transactional, entity-based reactive mappings and sequences.

A setter opens a scoped mutable draft. Successful synchronous edits are
staged together and become visible at the next flush. Read proxies retain
entity identity through moves; dictionary methods have normal Python
semantics. Use subscription for keys such as ``items`` or ``get``.
"""

from __future__ import annotations

import copy
import inspect
from bisect import bisect_left, insort
from collections import deque
from collections.abc import Callable, Iterable, Iterator, Mapping, MutableMapping, MutableSequence, Sequence
from dataclasses import dataclass
from typing import Any, overload
from weakref import WeakKeyDictionary

from . import _warnings
from ._vector import Vector
from .reactivity import _core
from .reactivity._actions import _register_optimistic_revert
from .reactivity._core import Signal, WriteInScopeError, untrack

__all__ = [
    "Store",
    "StoreList",
    "Draft",
    "DraftList",
    "StoreSetter",
    "DraftExpiredError",
    "create_store",
    "create_projection",
    "create_optimistic_store",
    "reconcile",
    "snapshot",
    "deep",
]

_ABSENT = object()


class DraftExpiredError(RuntimeError):
    """A draft was used after its setter or deriving function finished."""


@dataclass(frozen=True, slots=True)
class ListChange:
    """Internal sequence edit. Indices refer to the state before this edit."""

    kind: str
    index: int = 0
    removed: tuple[Any, ...] = ()
    added: tuple[Any, ...] = ()


@dataclass(frozen=True, slots=True)
class _State:
    data: Any
    revision: int = 0


class _Root:
    __slots__ = ("optimistic", "derivation", "authoritative", "authoritative_version")

    def __init__(self) -> None:
        self.optimistic = False
        self.authoritative: dict[_Node, Any] | None = None
        self.authoritative_version: Signal[int] = Signal(0)
        self.derivation: _core.Computation | None = None

    def ready(self) -> None:
        if _core._authoritative_depth:
            self.authoritative_version()
        comp = self.derivation
        if comp is not None:
            comp._update_if_necessary()
            # Ready reads depend on their properties. Pending/error reads also
            # subscribe to the producer so that an eventual landing retries them.
            if comp._error is not None or (comp._async is not None and comp._async.inflight):
                comp._read()
            else:
                untrack(comp._read)
        if _core._probe_depth:
            tx = _core._tx
            if self.optimistic or (tx is not None and self in tx.affected):
                _core._probe_mark()
                _core._probe_register()


def _lookup(data: Any, key: Any) -> Any:
    try:
        return data[key]
    except (KeyError, IndexError):
        return _ABSENT


def _same(a: Any, b: Any) -> bool:
    return not _core._changed(_core._DEFAULT_EQUALS, a, b)


class _Node:
    __slots__ = (
        "state",
        "properties",
        "indices",
        "membership",
        "length",
        "keys",
        "version",
        "parents",
        "root",
        "proxy",
        "history",
        "__weakref__",
    )

    def __init__(self, data: Any, root: _Root | None = None, seen: dict[int, Any] | None = None) -> None:
        if not isinstance(data, (Mapping, list, tuple, Vector)):
            raise TypeError("A store root must be a mapping or sequence; use create_signal for scalar state")
        self.root = root or _Root()
        self.properties: dict[Any, Signal[Any]] = {}
        self.indices: list[int] = []
        self.membership: dict[Any, Signal[bool]] = {}
        self.parents: WeakKeyDictionary[_Node, int] = WeakKeyDictionary()
        self.proxy: Any = None
        self.history: deque[tuple[int, tuple[ListChange, ...]]] = deque(maxlen=64)
        seen = {} if seen is None else seen
        if id(data) in seen:
            raise ValueError("Cyclic store data isn't supported")
        seen[id(data)] = None
        try:
            encoded: Any
            if isinstance(data, Mapping):
                encoded = {k: _encode(v, self.root, seen) for k, v in data.items()}
            else:
                encoded = Vector(_encode(v, self.root, seen) for v in data)
        finally:
            seen.pop(id(data), None)
        self.state: Signal[_State] = Signal(_State(encoded), equals=False)
        self.length: Signal[int] = Signal(len(encoded))
        self.keys: Signal[int] = Signal(0)
        self.version: Signal[int] = Signal(0)
        for value in encoded.values() if isinstance(encoded, dict) else encoded:
            self._link(value, 1)

    def _link(self, value: Any, amount: int) -> None:
        if isinstance(value, _Node):
            count = value.parents.get(self, 0) + amount
            if count:
                value.parents[self] = count
            else:
                value.parents.pop(self, None)

    def visible(self) -> Any:
        if _core._authoritative_depth and self.root.authoritative is not None:
            return self.root.authoritative.get(self, self.state.peek().data)
        return self.state.peek().data

    def read(self, key: Any) -> Any:
        self.root.ready()
        if _core._current_observer is not None or _core._probe_depth:
            sig = self.properties.get(key)
            if sig is None:
                sig = self.properties[key] = Signal(_lookup(self.state._value.data, key))
                if isinstance(self.state._value.data, Vector):
                    insort(self.indices, key)
                if self.state._staged:
                    sig._set(_lookup(self.state._latest().data, key))
                held = _core._held.get(self.state)
                if held is not None:
                    shown = _lookup(held.data, key)
                    if not _same(shown, sig._value):
                        _core._hold(sig, shown)
            sig()
        # The container's revealed revision also covers properties that weren't
        # observed before a transition began. Read history can't change visibility.
        value = _lookup(self.visible(), key)
        if value is _ABSENT:
            if isinstance(self.state._value.data, dict):
                raise KeyError(key)
            raise IndexError("list index out of range")
        return _wrap(value)

    def publish(self, data: Any, changes: list[ListChange], touched: set[Any]) -> None:
        old = self.state._latest()
        old_data = old.data
        if isinstance(data, dict):
            changed = {k for k in touched if not _same(_lookup(old_data, k), _lookup(data, k))}
            if not changed:
                return
            structural = any((k in old_data) != (k in data) for k in changed)
            for k in changed:
                self._link(_lookup(old_data, k), -1)
                self._link(_lookup(data, k), 1)
        else:
            if not changes:
                return
            structural = len(old_data) != len(data)
            changed = set()
            reset = False
            for change in changes:
                if change.kind == "reset":
                    reset = True
                    break
                for value in change.removed:
                    self._link(value, -1)
                for value in change.added:
                    self._link(value, 1)
                if change.kind == "set":
                    changed.add(change.index)
                else:
                    end = change.index + max(len(change.removed), len(change.added))
                    shifted = len(change.removed) != len(change.added)
                    start_slot = bisect_left(self.indices, change.index)
                    end_slot = len(self.indices) if shifted else bisect_left(self.indices, end)
                    changed.update(self.indices[start_slot:end_slot])
            if reset:
                # General replacement is deliberately the O(n) fallback.
                for value in old_data:
                    self._link(value, -1)
                for value in data:
                    self._link(value, 1)
                changed.update(self.properties)
        revision = old.revision + 1
        self.state._set(_State(data, revision))
        if changes:
            self.history.append((revision, tuple(changes)))
        if structural:
            self.keys._set(self.keys._latest() + 1)
        self.length._set(len(data))
        for key in changed:
            sig = self.properties.get(key)
            if sig is not None:
                sig._set(_lookup(data, key))
            member = self.membership.get(key)
            if member is not None:
                member._set(key in data)

    def bump(self, seen: set[_Node]) -> None:
        if self in seen:
            return
        seen.add(self)
        self.version._set(self.version._latest() + 1)
        for parent in tuple(self.parents):
            parent.bump(seen)


def _encode(value: Any, root: _Root, seen: dict[int, Any] | None = None) -> Any:
    if isinstance(value, _Proxy):
        value._check()
        node = value._node
        if node.root is root:
            return node
        value = snapshot(value)
    if isinstance(value, _Node):
        return value
    if isinstance(value, (Mapping, list, tuple, Vector)):
        return _Node(value, root, seen)
    return copy.deepcopy(value)


def _wrap(value: Any, session: _Session | None = None) -> Any:
    if not isinstance(value, _Node):
        return value
    if session is not None:
        session.check()
        proxy = session.proxies.get(value)
        if proxy is None:
            cls: Any = Draft if isinstance(value.state._value.data, dict) else DraftList
            proxy = session.proxies[value] = cls(value, session)
        return proxy
    if value.proxy is None:
        cls = Store if isinstance(value.state._value.data, dict) else StoreList
        value.proxy = cls(value)
    return value.proxy


class _Session:
    __slots__ = ("active", "states", "changes", "touched", "proxies")

    def __init__(self) -> None:
        self.active = True
        self.states: dict[_Node, Any] = {}
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
        self.check()
        return self.states.get(node, node.state._latest().data)

    def write(self, node: _Node, key: Any, value: Any) -> None:
        data = self.data(node)
        value = _encode(value, node.root)
        old = _lookup(data, key)
        if _same(old, value):
            return
        if isinstance(data, dict):
            if node not in self.states:
                data = dict(data)
            data[key] = value
            self.touched.setdefault(node, set()).add(key)
        else:
            key = data._index(key)
            old = data[key]
            data = data.set(key, value)
            self.changes.setdefault(node, []).append(ListChange("set", key, (old,), (value,)))
        self.states[node] = data

    def delete_key(self, node: _Node, key: Any) -> None:
        data = self.data(node)
        if key not in data:
            raise KeyError(key)
        if node not in self.states:
            data = dict(data)
        del data[key]
        self.states[node] = data
        self.touched.setdefault(node, set()).add(key)

    def splice(self, node: _Node, start: int, delete: int, values: Iterable[Any]) -> None:
        data = self.data(node)
        added = tuple(_encode(v, node.root) for v in values)
        removed = tuple(data[i] for i in range(start, start + delete))
        if not removed and not added:
            return
        self.states[node] = data.splice(start, delete, added)
        self.changes.setdefault(node, []).append(ListChange("splice", start, removed, added))

    def replace_list(self, node: _Node, values: Iterable[Any]) -> None:
        self.check()
        self.states[node] = Vector(_encode(v, node.root) for v in values)
        self.changes[node] = [ListChange("reset")]

    def commit(self) -> None:
        bumped: set[_Node] = set()
        for node, data in self.states.items():
            before = node.state._latest()
            node.publish(data, self.changes.get(node, []), self.touched.get(node, set()))
            if before is not node.state._latest():
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
        self._check()
        if self._session is not None:
            return self._session.data(self._node)
        self._node.root.ready()
        return self._node.visible()

    def _read(self, key: Any) -> Any:
        if self._session is not None:
            return _wrap(self._data()[key], self._session)
        return self._node.read(key)

    def _wyb_affect_node(self) -> Any:
        return self._node.root

    def _wyb_refresh(self) -> Any:
        comp = self._node.root.derivation
        if comp is None:
            raise TypeError("Only derived stores can be refreshed")
        comp._refresh()
        return comp

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("Store is read-only; mutate a draft inside its setter")

    def __len__(self) -> int:
        if self._session is not None:
            return len(self._data())
        self._node.root.ready()
        self._node.length()
        return len(self._node.visible())

    def __eq__(self, other: Any) -> bool:
        return bool(deep(self) == deep(other))

    __hash__ = None


class Store[S](_Proxy, Mapping[str, Any]):
    """Read-only reactive mapping with optional attribute access to data keys.

    Missing subscriptions raise KeyError; missing attributes raise AttributeError.
    Mapping methods take precedence over data keys: use ``store["items"]``.
    """

    __slots__ = ()

    def __getitem__(self, key: str) -> Any:
        return self._read(key)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._read(name)
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __iter__(self) -> Iterator[str]:
        if self._session is None:
            self._node.keys()
        return iter(self._data())

    def __contains__(self, key: object) -> bool:
        if self._session is not None:
            return key in self._data()
        node = self._node
        node.root.ready()
        sig = node.membership.get(key)
        if sig is None:
            sig = node.membership[key] = Signal(key in node.state._value.data)
            if node.state._staged:
                sig._set(key in node.state._latest().data)
        sig()
        return key in node.visible()

    def __repr__(self) -> str:
        return f"Store({snapshot(self)!r})"


class StoreList[T](_Proxy, Sequence[T]):
    """Read-only reactive sequence. Entity proxies survive reorders."""

    __slots__ = ()

    @overload
    def __getitem__(self, index: int) -> T: ...

    @overload
    def __getitem__(self, index: slice) -> list[T]: ...

    def __getitem__(self, index: int | slice) -> T | list[T]:
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self)))]
        if not isinstance(index, int):
            raise TypeError("list indices must be integers or slices")
        if index < 0:
            index += len(self)
        if index < 0:
            raise IndexError("list index out of range")
        return self._read(index)

    def __iter__(self) -> Iterator[T]:
        for i in range(len(self)):
            yield self[i]

    def __repr__(self) -> str:
        return f"StoreList({snapshot(self)!r})"

    def _wyb_list_state(self) -> _State:
        self._node.root.ready()
        return self._node.state()

    def _wyb_changes_since(self, revision: int) -> tuple[ListChange, ...] | None:
        current = self._node.state.peek().revision
        if current == revision:
            return ()
        records = [(r, changes) for r, changes in self._node.history if revision < r <= current]
        if not records or records[0][0] != revision + 1 or records[-1][0] != current:
            return None
        return tuple(change for _, changes in records for change in changes)


class Draft[S](Store[S], MutableMapping[str, Any]):
    """A mapping draft that expires when its callback returns."""

    __slots__ = ()

    def __setitem__(self, key: str, value: Any) -> None:
        assert self._session is not None
        self._session.write(self._node, key, value)

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value

    def __delitem__(self, key: str) -> None:
        assert self._session is not None
        self._session.delete_key(self._node, key)

    def __delattr__(self, name: str) -> None:
        try:
            del self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


class DraftList[T](StoreList[T], MutableSequence[T]):
    """A sequence draft with standard Python mutation methods."""

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
        data = self._data()
        if isinstance(index, slice):
            start, stop, step = index.indices(len(data))
            if step == 1:
                session.splice(self._node, start, max(0, stop - start), ())
            else:
                for i in sorted(range(start, stop, step), reverse=True):
                    session.splice(self._node, i, 1, ())
        else:
            session.splice(self._node, data._index(index), 1, ())

    def insert(self, index: int, value: T) -> None:
        """Insert a value at a draft index."""
        session = self._session
        assert session is not None
        n = len(self)
        index = max(0, n + index) if index < 0 else min(index, n)
        session.splice(self._node, index, 0, (value,))

    def extend(self, values: Iterable[T]) -> None:
        """Append values in one recorded splice."""
        session = self._session
        assert session is not None
        session.splice(self._node, len(self), 0, tuple(values))

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


def _merge(session: _Session, node: _Node, data: Any, key: str | None) -> None:
    if isinstance(data, _Proxy):
        data = snapshot(data)
    current = session.data(node)
    if isinstance(current, dict) and isinstance(data, Mapping):
        for k in tuple(current):
            if k not in data:
                session.delete_key(node, k)
        for k, value in data.items():
            old = _lookup(session.data(node), k)
            if isinstance(old, _Node) and _compatible(old, value):
                _merge(session, old, value, key)
            else:
                session.write(node, k, value)
    elif isinstance(current, Vector) and isinstance(data, (Sequence, Vector)) and not isinstance(data, (str, bytes)):
        by_key: dict[Any, deque[_Node]] = {}
        if key is not None:
            for item in current:
                if isinstance(item, _Node) and isinstance(item.state._value.data, dict):
                    ident = _lookup(session.data(item), key)
                    if ident is not _ABSENT:
                        by_key.setdefault(ident, deque()).append(item)
        result = []
        for item in data:
            bucket = by_key.get(item.get(key, _ABSENT)) if key is not None and isinstance(item, Mapping) else None
            if bucket:
                old = bucket.popleft()
                _merge(session, old, item, key)
                result.append(old)
            else:
                result.append(_encode(item, node.root))
        if len(current) != len(result) or any(not _same(a, b) for a, b in zip(current, result)):
            session.replace_list(node, result)
    else:
        raise TypeError("A store's root container type can't change")


def _compatible(node: _Node, data: Any) -> bool:
    current = node.state._value.data
    return (
        isinstance(current, dict)
        and isinstance(data, Mapping)
        or isinstance(current, Vector)
        and isinstance(data, (list, tuple, StoreList))
    )


def _modify(session: _Session, node: _Node, modifier: Any) -> None:
    if isinstance(modifier, _Reconcile):
        _merge(session, node, modifier.data, modifier.key)
    elif callable(modifier):
        result = modifier(_wrap(node, session))
        if inspect.isawaitable(result):
            if inspect.iscoroutine(result):
                result.close()
            raise TypeError("Store setters are synchronous; await work in an action before opening a draft")
        if result is not None:
            _merge(session, node, result, None)
    elif isinstance(modifier, (Mapping, list, tuple, StoreList)):
        _merge(session, node, modifier, None)
    else:
        raise TypeError("set_store expects a draft callback, reconcile result, or replacement data")


class StoreSetter[D]:
    """Apply an atomic draft edit. Exceptions discard all changes from the call."""

    __slots__ = ("_node",)

    def __init__(self, node: _Node) -> None:
        self._node = node

    def __call__(self, modifier: Callable[[D], Any] | Mapping[str, Any] | list[Any] | _Reconcile) -> None:
        """Stage a synchronous atomic edit or replacement."""
        if _core._current_observer is not None and _warnings.DEV_MODE:
            raise WriteInScopeError(
                "Cannot write a store inside a tracking scope; use an effect's apply stage or an action"
            )
        session = _Session()
        try:
            _modify(session, self._node, modifier)
            session.commit()
        finally:
            session.close()


@overload
def create_store[T](initial: list[T], seed: None = None) -> tuple[StoreList[T], StoreSetter[DraftList[T]]]: ...


@overload
def create_store[S: Mapping[str, Any]](initial: S, seed: None = None) -> tuple[Store[S], StoreSetter[Draft[S]]]: ...


@overload
def create_store(initial: Callable[..., Any], seed: Any = None) -> tuple[Any, StoreSetter[Any]]: ...


def create_store(initial: Any, seed: Any = None) -> tuple[Any, StoreSetter]:
    """Create a reactive mapping or sequence and its atomic draft setter.

    A deriving function may return data or mutate its draft, synchronously or
    asynchronously. Its reads are tracked and its writes are staged together.
    """
    if callable(initial):
        node = _Node({} if seed is None else seed)
        _run_projection(node, initial)
    else:
        node = _Node(initial)
    return _wrap(node), StoreSetter(node)


def _run_projection(node: _Node, fn: Callable[..., Any]) -> None:
    takes_draft = _core._positional_count(fn) != 0

    def compute() -> Any:
        session = _Session()
        try:
            result = fn(_wrap(node, session)) if takes_draft else fn()
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
                        landing.states, session.states = session.states, {}
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


def create_projection(fn: Callable[..., Any], initial: Any = None) -> Any:
    """Create a read-only derived store with memo readiness and refresh semantics."""
    node = _Node({} if initial is None else initial)
    _run_projection(node, fn)
    return _wrap(node)


def create_optimistic_store(source: Any, initial: Any = None) -> tuple[Any, Callable[[Any], None]]:
    """Layer optimistic draft edits over a reactive authoritative source.

    Active edits replay in submission order when the source changes. They are
    removed together when their enclosing transition settles. Draft callbacks
    must be deterministic: replay mustn't perform network or other side effects.
    """
    derived = callable(source)
    state = ({} if initial is None else initial) if derived else source
    node = _Node(state)
    base = [snapshot(state)]
    overlays: list[Any] = []

    def capture_base(session: _Session) -> None:
        captured: dict[_Node, Any] = {}
        queue = [node]
        while queue:
            current = queue.pop()
            if current in captured:
                continue
            data = session.data(current)
            captured[current] = dict(data) if isinstance(data, dict) else data
            queue.extend(
                value for value in (data.values() if isinstance(data, dict) else data) if isinstance(value, _Node)
            )
        node.root.authoritative = captured
        version = node.root.authoritative_version
        version._set(version._latest() + 1, _core._O_REVEAL)

    def rebuild() -> None:
        session = _Session()
        try:
            _merge(session, node, base[0], "id")
            capture_base(session)
            for modifier in overlays:
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
            overlays.append(modifier)
            node.root.optimistic = True
        finally:
            _core._optimistic_depth -= 1

        def revert() -> None:
            overlays.clear()
            node.root.optimistic = False
            _core._optimistic_depth += 1
            try:
                untrack(rebuild)
            finally:
                _core._optimistic_depth -= 1

        _register_optimistic_revert(revert)

    return _wrap(node), set_optimistic


@dataclass(frozen=True, slots=True)
class _Reconcile:
    data: Any
    key: str | None


def reconcile(data: Any, key: str | None = "id") -> Any:
    """Prepare replacement data, preserving matched list entity identities.

    ``key=None`` replaces list entities positionally. Duplicate keys are matched
    in occurrence order, without assigning the same entity to multiple rows.
    """
    return _Reconcile(snapshot(data), key)


def _snapshot(value: Any, track: bool, memo: dict[int, Any]) -> Any:
    if isinstance(value, _Proxy):
        value._check()
        node = value._node
        if id(node) in memo:
            return memo[id(node)]
        if value._session is not None:
            data = value._session.data(node)
        else:
            node.root.ready()
            if track:
                node.version()
            data = node.visible()
        result: Any = {} if isinstance(data, dict) else []
        memo[id(node)] = result
        if isinstance(data, dict):
            result.update((k, _snapshot(_wrap(v, value._session), False, memo)) for k, v in data.items())
        else:
            result.extend(_snapshot(_wrap(v, value._session), False, memo) for v in data)
        return result
    return copy.deepcopy(value)


def snapshot(value: Any) -> Any:
    """Return a detached, untracked copy of the currently visible state."""
    return untrack(lambda: _snapshot(value, False, {}))


def deep(value: Any) -> Any:
    """Return a detached snapshot, tracking changes only within this subtree."""
    return _snapshot(value, True, {})
