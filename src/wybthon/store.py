"""Reactive stores for nested state, matching SolidJS 2.0's draft-first model.

Stores provide fine-grained reactive access to nested objects and
lists. Each path through the store is backed by its own
[`Signal`][wybthon.Signal], so reading `store.user.name` only
subscribes the current computation to that specific leaf, not to the
entire store.

Writes are **draft-first**: the setter hands you a mutable draft of the
state and you mutate it directly with normal Python. There is no path
syntax and no `produce` wrapper; mutating the draft is just how stores
work. Like signal writes, store writes are staged and become visible
on the next flush.

Public surface:

- [`create_store`][wybthon.create_store]: build a store from an initial
  value, or a **derived store** from a function; returns
  `(store, set_store)`.
- [`create_projection`][wybthon.create_projection]: a read-only store
  derived from reactive sources, updated fine-grained.
- [`create_optimistic_store`][wybthon.create_optimistic_store]: a store
  whose writes revert when in-flight [`action`][wybthon.action]s settle.
- [`reconcile`][wybthon.reconcile]: diff external data into a store,
  preserving object identity for unchanged items.
- [`store_path`][wybthon.store_path]: opt-in path-style setter helper.
- [`snapshot`][wybthon.snapshot]: the plain, non-reactive data behind a
  store proxy.
- [`deep`][wybthon.deep]: a plain snapshot that subscribes to every
  nested change.

Example:
    ```python
    from wybthon import create_store, reconcile

    store, set_store = create_store({
        "count": 0,
        "user": {"name": "Ada", "age": 30},
        "todos": [
            {"id": 1, "text": "Learn Wybthon", "done": False},
        ],
    })

    store.count           # 0
    store.user.name       # "Ada"
    store.todos[0].text   # "Learn Wybthon"

    def bump(s):
        s.count += 1
        s.user.name = "Jane"
        s.todos[0].done = True
        s.todos.append({"id": 2, "text": "New", "done": False})

    set_store(bump)

    set_store(reconcile(fetched_state))
    ```

See Also:
    - [Reactivity guide](../concepts/reactivity.md)
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from . import _warnings
from .reactivity import _core
from .reactivity._actions import _register_optimistic_revert
from .reactivity._core import Signal, WriteInScopeError, untrack
from .reactivity._primitives import create_render_effect

__all__ = [
    "create_store",
    "create_projection",
    "create_optimistic_store",
    "reconcile",
    "store_path",
    "snapshot",
    "deep",
]


def _getattribute(obj: Any, name: str) -> Any:
    return object.__getattribute__(obj, name)


def _raw_get(raw: Any, key: Any) -> Any:
    if isinstance(raw, dict):
        return raw.get(key)
    if isinstance(raw, (list, tuple)):
        try:
            return raw[key]
        except (IndexError, TypeError):
            return None
    return getattr(raw, key, None)


class _StoreRoot:
    """Per-store bookkeeping shared by every node: the deep-version signal."""

    __slots__ = ("version",)

    def __init__(self) -> None:
        self.version: Signal[int] = Signal(0)

    def bump(self) -> None:
        self.version._set(self.version._latest() + 1)


class _StoreNode:
    """Internal node holding one [`Signal`][wybthon.Signal] per property.

    Child nodes are cached by key so that proxy reads and draft writes
    for the same path always resolve to the same `Signal` instances.
    """

    __slots__ = ("_signals", "_raw", "_children", "_proxy", "_draft_proxy", "_root")

    def __init__(self, raw: Any, root: _StoreRoot | None = None) -> None:
        self._signals: dict[Any, Signal[Any]] = {}
        self._raw: Any = raw
        self._children: dict[Any, _StoreNode] = {}
        self._proxy: Any = None
        self._draft_proxy: Any = None
        self._root: _StoreRoot = root if root is not None else _StoreRoot()

    def _get_signal(self, key: Any) -> Signal[Any]:
        sig = self._signals.get(key)
        if sig is None:
            sig = Signal(_raw_get(self._raw, key))
            self._signals[key] = sig
        return sig

    def _get_child(self, key: Any) -> _StoreNode:
        """Return (or create) a cached child node for `key`."""
        child = self._children.get(key)
        if child is None:
            child = _StoreNode(_raw_get(self._raw, key), self._root)
            self._children[key] = child
        return child

    def _set_value(self, key: Any, value: Any) -> None:
        raw = self._raw
        if isinstance(raw, (dict, list)):
            raw[key] = value
        else:
            setattr(raw, key, value)

        sig = self._signals.get(key)
        if sig is not None:
            sig._set(value)
        else:
            self._signals[key] = Signal(value)

        child = self._children.get(key)
        if child is not None:
            if isinstance(value, (dict, list)):
                child._replace_raw(value)
            else:
                self._children.pop(key, None)
        self._root.bump()

    def _replace_raw(self, new_raw: Any) -> None:
        """Replace the underlying raw data and update all affected signals."""
        signals = self._signals
        children = self._children
        self._raw = new_raw

        if isinstance(new_raw, dict):
            keys = set(new_raw.keys()) | set(signals.keys())
        elif isinstance(new_raw, (list, tuple)):
            keys = set(range(len(new_raw))) | {k for k in signals if isinstance(k, int)}
        else:
            keys = set(signals.keys())

        for key in keys:
            new_val = _raw_get(new_raw, key)
            sig = signals.get(key)
            if sig is not None:
                sig._set(new_val)
            child = children.get(key)
            if child is not None:
                if isinstance(new_val, (dict, list)):
                    child._replace_raw(new_val)
                else:
                    children.pop(key, None)

        if isinstance(new_raw, (list, tuple)) and "length" in signals:
            signals["length"]._set(len(new_raw))
        self._root.bump()


def _wrap_value(value: Any, node: _StoreNode, *, draft: bool = False) -> Any:
    """Wrap a raw value in a reactive proxy backed by `node`.

    Read proxies and draft proxies are cached separately per node so
    repeated reads of the same path return the same proxy object
    (stable identity).
    """
    if isinstance(value, (dict, list)):
        expected: type
        if isinstance(value, dict):
            expected = _DraftProxy if draft else _StoreProxy
        else:
            expected = _DraftListProxy if draft else _StoreListProxy
        cached = node._draft_proxy if draft else node._proxy
        if type(cached) is expected:
            return cached
        proxy: Any = expected(node)
        if draft:
            node._draft_proxy = proxy
        else:
            node._proxy = proxy
        return proxy
    return value


class _StoreProxy:
    """Reactive read proxy for dict-like store objects.

    Attribute reads track the corresponding `Signal`; nested dicts and
    lists are lazily wrapped in their own proxies via cached child
    nodes. Writes must go through the store setter's draft.
    """

    __slots__ = ("_node",)

    def __init__(self, node: _StoreNode) -> None:
        object.__setattr__(self, "_node", node)

    def _read(self, key: Any) -> Any:
        node: _StoreNode = _getattribute(self, "_node")
        val = node._get_signal(key)()
        if isinstance(val, (dict, list)):
            child = node._get_child(key)
            child._raw = val
            return _wrap_value(val, child)
        return val

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            return _getattribute(self, name)
        return _StoreProxy._read(self, name)

    def __getitem__(self, key: Any) -> Any:
        return _StoreProxy._read(self, key)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        raise AttributeError("Store is read-only. Mutate the draft inside set_store(lambda s: ...) instead.")

    def __setitem__(self, key: Any, value: Any) -> None:
        raise TypeError("Store is read-only. Mutate the draft inside set_store(lambda s: ...) instead.")

    def __repr__(self) -> str:
        node: _StoreNode = _getattribute(self, "_node")
        return f"Store({node._raw!r})"

    def __eq__(self, other: Any) -> bool:
        node: _StoreNode = _getattribute(self, "_node")
        if isinstance(other, _StoreProxy):
            other_node: _StoreNode = _getattribute(other, "_node")
            return bool(node._raw == other_node._raw)
        if isinstance(other, dict):
            return bool(node._raw == other)
        return NotImplemented

    def __contains__(self, key: Any) -> bool:
        node: _StoreNode = _getattribute(self, "_node")
        node._root.version()
        return key in node._raw

    def __iter__(self) -> Any:
        node: _StoreNode = _getattribute(self, "_node")
        node._root.version()
        return iter(node._raw)

    def __len__(self) -> int:
        node: _StoreNode = _getattribute(self, "_node")
        node._root.version()
        return len(node._raw)

    __hash__ = object.__hash__


class _StoreListProxy:
    """Reactive read proxy for list-like store values.

    Index reads track the corresponding `Signal`. Supports `len()`,
    iteration, and `in` checks; mutations must go through the store
    setter's draft.
    """

    __slots__ = ("_node",)

    def __init__(self, node: _StoreNode) -> None:
        object.__setattr__(self, "_node", node)

    def __getitem__(self, index: Any) -> Any:
        node: _StoreNode = _getattribute(self, "_node")
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self)))]
        if index < 0:
            index += len(node._raw)
        val = node._get_signal(index)()
        if isinstance(val, (dict, list)):
            child = node._get_child(index)
            child._raw = val
            return _wrap_value(val, child)
        return val

    def __len__(self) -> int:
        node: _StoreNode = _getattribute(self, "_node")
        node._get_signal("length")()
        return len(node._raw)

    def __iter__(self) -> Any:
        node: _StoreNode = _getattribute(self, "_node")
        node._get_signal("length")()
        for i in range(len(node._raw)):
            yield self[i]

    def __contains__(self, item: Any) -> bool:
        node: _StoreNode = _getattribute(self, "_node")
        node._root.version()
        return item in node._raw

    def __repr__(self) -> str:
        node: _StoreNode = _getattribute(self, "_node")
        return f"StoreList({node._raw!r})"

    def __eq__(self, other: Any) -> bool:
        node: _StoreNode = _getattribute(self, "_node")
        if isinstance(other, _StoreListProxy):
            other_node: _StoreNode = _getattribute(other, "_node")
            return bool(node._raw == other_node._raw)
        if isinstance(other, list):
            return bool(node._raw == other)
        return NotImplemented

    __hash__ = object.__hash__


# --------------- draft proxies (handed to set_store callbacks) ---------------


class _DraftProxy(_StoreProxy):
    """Writable draft over a dict store node.

    Handed to `set_store(fn)` callbacks. Reads are untracked and see
    the latest written value; writes apply to the underlying raw data
    and stage exactly the affected leaf signals, which become visible
    on the next flush.
    """

    __slots__ = ()

    def _read(self, key: Any) -> Any:
        node: _StoreNode = _getattribute(self, "_node")
        val = _raw_get(node._raw, key)
        if isinstance(val, (dict, list)):
            child = node._get_child(key)
            child._raw = val
            return _wrap_value(val, child, draft=True)
        return val

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            return _getattribute(self, name)
        return _DraftProxy._read(self, name)

    def __getitem__(self, key: Any) -> Any:
        return _DraftProxy._read(self, key)

    def __contains__(self, key: Any) -> bool:
        node: _StoreNode = _getattribute(self, "_node")
        return key in node._raw

    def __iter__(self) -> Any:
        node: _StoreNode = _getattribute(self, "_node")
        return iter(node._raw)

    def __len__(self) -> int:
        node: _StoreNode = _getattribute(self, "_node")
        return len(node._raw)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        node: _StoreNode = _getattribute(self, "_node")
        node._set_value(name, _plain(value))

    def __setitem__(self, key: Any, value: Any) -> None:
        node: _StoreNode = _getattribute(self, "_node")
        node._set_value(key, _plain(value))

    def __delitem__(self, key: Any) -> None:
        node: _StoreNode = _getattribute(self, "_node")
        raw = node._raw
        if isinstance(raw, dict):
            raw.pop(key, None)
        node._replace_raw(raw)

    def __delattr__(self, name: str) -> None:
        self.__delitem__(name)

    def update(self, values: dict[str, Any]) -> None:
        """Merge `values` into this draft (dict-style bulk write)."""
        node: _StoreNode = _getattribute(self, "_node")
        for k, v in values.items():
            node._set_value(k, _plain(v))

    __hash__ = object.__hash__


class _DraftListProxy(_StoreListProxy):
    """Writable draft over a list store node.

    Supports index assignment plus `append`, `insert`, `pop`, `remove`,
    `extend`, `sort`, `reverse`, and `clear`, staging index and length
    subscribers.
    """

    __slots__ = ()

    def __getitem__(self, index: Any) -> Any:
        node: _StoreNode = _getattribute(self, "_node")
        raw: list[Any] = node._raw
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(raw)))]
        if index < 0:
            index += len(raw)
        val = raw[index]
        if isinstance(val, (dict, list)):
            child = node._get_child(index)
            child._raw = val
            return _wrap_value(val, child, draft=True)
        return val

    def __len__(self) -> int:
        node: _StoreNode = _getattribute(self, "_node")
        return len(node._raw)

    def __iter__(self) -> Any:
        node: _StoreNode = _getattribute(self, "_node")
        for i in range(len(node._raw)):
            yield self[i]

    def __contains__(self, item: Any) -> bool:
        node: _StoreNode = _getattribute(self, "_node")
        return item in node._raw

    def __setitem__(self, index: Any, value: Any) -> None:
        node: _StoreNode = _getattribute(self, "_node")
        if isinstance(index, slice):
            node._raw[index] = [_plain(v) for v in value]
            node._replace_raw(node._raw)
            return
        if index < 0:
            index += len(node._raw)
        node._set_value(index, _plain(value))

    def __delitem__(self, index: Any) -> None:
        node: _StoreNode = _getattribute(self, "_node")
        del node._raw[index]
        node._replace_raw(node._raw)

    def _mutate(self, op: Callable[[list[Any]], Any]) -> Any:
        node: _StoreNode = _getattribute(self, "_node")
        result = op(node._raw)
        node._replace_raw(node._raw)
        return result

    def append(self, value: Any) -> None:
        """Append `value`, notifying index and length subscribers."""
        self._mutate(lambda raw: raw.append(_plain(value)))

    def extend(self, values: Any) -> None:
        """Append every item in `values`."""
        self._mutate(lambda raw: raw.extend(_plain(v) for v in values))

    def insert(self, index: int, value: Any) -> None:
        """Insert `value` at `index`, shifting later items."""
        self._mutate(lambda raw: raw.insert(index, _plain(value)))

    def pop(self, index: int = -1) -> Any:
        """Remove and return the item at `index` (default: last)."""
        return self._mutate(lambda raw: raw.pop(index))

    def remove(self, value: Any) -> None:
        """Remove the first occurrence of `value`."""
        self._mutate(lambda raw: raw.remove(_plain(value)))

    def clear(self) -> None:
        """Remove every item."""
        self._mutate(lambda raw: raw.clear())

    def sort(self, *, key: Any = None, reverse: bool = False) -> None:
        """Sort in place."""
        self._mutate(lambda raw: raw.sort(key=key, reverse=reverse))

    def reverse(self) -> None:
        """Reverse in place."""
        self._mutate(lambda raw: raw.reverse())

    __hash__ = object.__hash__


def _plain(value: Any) -> Any:
    """Strip store proxies from a value being written into a store."""
    if isinstance(value, (_StoreProxy, _StoreListProxy)):
        return _getattribute(value, "_node")._raw
    return value


def _make_draft(node: _StoreNode) -> Any:
    raw = node._raw
    if isinstance(raw, (dict, list)):
        return _wrap_value(raw, node, draft=True)
    return raw


def _make_proxy(node: _StoreNode) -> Any:
    raw = node._raw
    if isinstance(raw, dict):
        return _StoreProxy(node)
    if isinstance(raw, list):
        return _StoreListProxy(node)
    return raw


def _apply_modifier(node: _StoreNode, modifier: Any, what: str) -> None:
    """Run a setter argument against `node`: a draft fn, a reconcile marker, or a value."""
    if isinstance(modifier, _ReconcileResult):
        modifier._apply(node)
        return
    if callable(modifier):
        result = modifier(_make_draft(node))
        if result is not None and result is not node._raw:
            _merge_data_into(node, _plain(result), None)
        return
    if isinstance(modifier, (dict, list)):
        _merge_data_into(node, _plain(modifier), None)
        return
    raise TypeError(f"{what}() takes a draft function, a reconcile() result, or replacement data")


def _merge_data_into(node: _StoreNode, data: Any, key: str | None) -> None:
    merged = _merge_data(node._raw, data, key)
    node._replace_raw(merged)


class _StoreSetter:
    """Callable that applies draft mutations to a store.

    Calling conventions, matching SolidJS 2.0 `setStore`:

    - `set_store(fn)`: `fn` receives a mutable **draft** of the state;
      mutate it with normal Python (attribute and index assignment,
      list methods). Only the leaf signals whose values actually
      changed notify. If `fn` returns a dict or list, that value is
      merged in as a shallow replacement.
    - `set_store(reconcile(data))`: merge external data in, preserving
      object identity for unchanged items (see
      [`reconcile`][wybthon.reconcile]).
    - `set_store(store_path("user", "name", "Ada"))`: path-style write
      (see [`store_path`][wybthon.store_path]).
    """

    __slots__ = ("_node",)

    def __init__(self, node: _StoreNode) -> None:
        self._node = node

    def __call__(self, modifier: Any) -> None:
        if _core._current_observer is not None and _warnings.DEV_MODE:
            raise WriteInScopeError(
                "Cannot write a store inside a tracking scope (memo, effect compute stage, or reactive "
                "hole). Derive the value with create_projection, or write from the apply stage of a "
                "split create_effect, an event handler, or an action."
            )
        _apply_modifier(self._node, modifier, "set_store")


def create_store(initial: Any, seed: Any = None) -> tuple[Any, _StoreSetter]:
    """Create a reactive store from an initial value or a deriving function.

    Args:
        initial: Initial state (a dict or list), or a **function** for a
            derived store. A function that accepts a draft mutates it
            on every run, like [`create_projection`][wybthon.create_projection];
            a zero-arg function's return value is reconciled into the
            store. Reads inside it are tracked.
        seed: Initial backing state for the derived form (defaults to
            an empty dict).

    Returns:
        A tuple `(store, set_store)` where `store` is a read-only
        reactive proxy that tracks reads per-path, and `set_store`
        applies **draft mutations**: call it with a function that
        receives a mutable draft, a [`reconcile`][wybthon.reconcile]
        result, or a [`store_path`][wybthon.store_path] write.

    Example:
        ```python
        store, set_store = create_store({"count": 0, "user": {"name": "Ada"}})

        store.count         # 0
        store.user.name     # "Ada"

        def rename(s):
            s.count += 1
            s.user.name = "Jane"

        set_store(rename)
        set_store(reconcile(fetched_state))

        # Derived store: re-runs when `todos` changes.
        stats, _ = create_store(lambda d: d.update({"total": len(todos())}), {"total": 0})
        ```
    """
    if callable(initial) and not isinstance(initial, (dict, list)):
        node = _StoreNode(seed if seed is not None else {})
        _run_projection(node, initial)
        return _make_proxy(node), _StoreSetter(node)
    node = _StoreNode(initial)
    return _make_proxy(node), _StoreSetter(node)


# --------------- projections ---------------


def _run_projection(node: _StoreNode, fn: Callable[..., Any]) -> None:
    draft = _make_draft(node)
    takes_draft = _core._positional_count(fn) != 0

    def compute() -> Any:
        if takes_draft:
            return fn(draft)
        return fn()

    def apply(result: Any) -> None:
        if result is not None and result is not node._raw:
            _merge_data_into(node, copy.deepcopy(snapshot(result)), "id")

    create_render_effect(compute, apply)


def create_projection(fn: Callable[..., Any], initial: Any = None) -> Any:
    """Create a read-only store derived from reactive sources.

    `fn` receives a mutable draft of the projection's state and runs
    inside a render-phase computation: any signals, memos, or other
    stores it reads become dependencies, and when they change `fn`
    re-runs against the same draft. Because writes go through
    fine-grained store signals, consumers re-render only for the paths
    that actually changed. A zero-arg `fn` may instead return the data
    to reconcile in.

    Matches SolidJS 2.0's `createProjection`.

    Args:
        fn: Draft mutator (or zero-arg producer). Reads are tracked.
        initial: Initial backing state (a dict or list). Defaults to an
            empty dict.

    Returns:
        A read-only store proxy.

    Example:
        ```python
        selected, set_selected = create_signal(1)

        flags = create_projection(
            lambda draft: draft.update({"selected_id": selected()}),
            {"selected_id": None},
        )
        ```
    """
    node = _StoreNode(initial if initial is not None else {})
    _run_projection(node, fn)
    return _make_proxy(node)


# --------------- optimistic stores ---------------


def create_optimistic_store(source: Any, initial: Any = None) -> tuple[Any, Callable[[Any], None]]:
    """Create a store whose writes revert when in-flight actions settle.

    Reads behave like a normal store. Writes (draft mutations through
    the returned setter) apply immediately; when every in-flight
    [`action`][wybthon.action] has settled, the store **reverts** to its
    base state: the tracked `source` function's latest result (derived
    form), or the initial value (value form). Pair it with actions that
    reconcile real data into a regular store; the optimistic overlay
    bridges the latency gap.

    Args:
        source: Either a tracked function returning the base state
            (derived form; re-runs and reconciles when its dependencies
            change) or a plain dict/list initial value.
        initial: Initial backing state for the derived form, used
            before `source` first runs. Defaults to an empty dict.

    Returns:
        A `(store, set_optimistic)` tuple. `set_optimistic(fn)` applies
        a draft mutation, like a store setter.

    Example:
        ```python
        todos, set_todos = create_store({"items": []})

        shown, set_shown = create_optimistic_store(lambda: deep(todos)["items"], [])

        @action
        async def add(title):
            set_shown(lambda s: s.append({"title": title, "saving": True}))
            saved = await api_create(title)
            set_todos(lambda s: s.items.append(saved))
        ```
    """
    derived = callable(source) and not isinstance(source, (dict, list))
    state: Any = (initial if initial is not None else {}) if derived else source
    node = _StoreNode(state)

    base: dict[str, Any] = {"value": copy.deepcopy(snapshot(state))}

    def _reconcile_to(data: Any) -> None:
        _merge_data_into(node, copy.deepcopy(data), "id")

    if derived:

        def track_base() -> Any:
            return copy.deepcopy(snapshot(source()))

        def apply_base(data: Any) -> None:
            base["value"] = data
            _reconcile_to(data)

        create_render_effect(track_base, apply_base)

    def revert() -> None:
        _reconcile_to(base["value"])

    def set_optimistic(modifier: Any) -> None:
        _apply_modifier(node, modifier, "set_optimistic")
        _register_optimistic_revert(lambda: untrack(revert))

    return _make_proxy(node), set_optimistic


# --------------- reconcile / store_path / snapshot / deep ---------------


def _merge_data(old: Any, new: Any, key: str | None) -> Any:
    """Merge `new` into `old` in place where container types match.

    Dicts are updated key by key; lists of dicts are matched by `key`
    so that unchanged items keep their **object identity** (which is
    what [`For`][wybthon.For] uses to preserve row DOM). Returns the
    merged value, which is `old` whenever an in-place merge happened.
    """
    if isinstance(old, dict) and isinstance(new, dict):
        for k in [k for k in old.keys() if k not in new]:
            del old[k]
        for k, v in new.items():
            if k in old:
                old[k] = _merge_data(old[k], v, key)
            else:
                old[k] = v
        return old
    if isinstance(old, list) and isinstance(new, list):
        if key:
            by_key: dict[Any, Any] = {}
            for item in old:
                if isinstance(item, dict) and key in item:
                    by_key.setdefault(item[key], item)
            merged: list[Any] = []
            for item in new:
                if isinstance(item, dict) and key in item and item[key] in by_key:
                    merged.append(_merge_data(by_key.pop(item[key]), item, key))
                else:
                    merged.append(item)
            old[:] = merged
        else:
            old[:] = new
        return old
    return new


class _ReconcileResult:
    """Marker wrapping data for [`reconcile`][wybthon.reconcile]."""

    __slots__ = ("_data", "_key")

    def __init__(self, data: Any, key: str | None) -> None:
        self._data = data
        self._key = key

    def _apply(self, node: _StoreNode) -> None:
        _merge_data_into(node, _plain(self._data), self._key)


def reconcile(data: Any, key: str | None = "id") -> _ReconcileResult:
    """Diff external data into a store, keeping identity for unchanged items.

    Matches SolidJS's `reconcile`. Pass the result to a store setter;
    instead of replacing the state wholesale, the incoming data is
    merged: dicts update key by key, and lists of dicts are matched by
    `key` so existing item objects are **updated in place** rather than
    replaced. Only the leaf signals whose values actually changed
    notify, and [`For`][wybthon.For] rows for unchanged items keep
    their DOM.

    Args:
        data: The incoming plain data (dict, list, or scalar).
        key: Dict key used to match list items. Defaults to `"id"`.
            Pass `None` to disable key matching (positional replace).

    Returns:
        A marker object recognized by the store setter.

    Example:
        ```python
        set_store(reconcile(fetched_state))
        ```
    """
    return _ReconcileResult(data, key)


def store_path(*path_and_value: Any) -> Callable[[Any], None]:
    """Build a path-style write for a store setter (opt-in helper).

    The last argument is the value (or an updater `(current) -> new`);
    everything before it is the path of keys and indices to walk. It
    returns a draft function, so it composes with everything a setter
    accepts.

    Example:
        ```python
        set_store(store_path("user", "address", "city", "Paris"))
        set_store(store_path("todos", 0, "done", lambda done: not done))
        ```
    """
    if len(path_and_value) < 2:
        raise TypeError("store_path() needs at least one key and a value")
    *path, value = path_and_value

    def write(draft: Any) -> None:
        target = draft
        for key in path[:-1]:
            target = target[key]
        last = path[-1]
        if callable(value):
            target[last] = value(target[last])
        else:
            target[last] = value

    return write


def snapshot(value: Any) -> Any:
    """Return the plain, non-reactive data behind a store proxy.

    Matches SolidJS 2.0's `snapshot` (the successor to `unwrap`).
    Reading the result doesn't subscribe to anything, so it's the right
    thing to hand to `json.dumps`, to compare, or to pass outside the
    reactive graph. Mutating it bypasses reactivity entirely; write
    through the setter instead.

    Args:
        value: A store proxy (or any value).

    Returns:
        The underlying dict/list for proxies; `value` unchanged
        otherwise.
    """
    if isinstance(value, (_StoreProxy, _StoreListProxy)):
        return _getattribute(value, "_node")._raw
    return value


def deep(value: Any) -> Any:
    """Read a store deeply: subscribe to every nested change and return plain data.

    Store tracking is normally per property. Use `deep` in the compute
    stage of a split effect when the whole structure matters, for
    example to persist or serialize it: the effect re-runs on any
    nested write and its apply stage receives a plain copy that's safe
    to read untracked.

    Example:
        ```python
        create_effect(lambda: deep(store), lambda data: save(json.dumps(data)))
        ```
    """
    if isinstance(value, (_StoreProxy, _StoreListProxy)):
        node: _StoreNode = _getattribute(value, "_node")
        node._root.version()
        return copy.deepcopy(node._raw)
    return value
