"""Reactive stores for nested state, matching SolidJS 2.0's draft-first model.

Stores provide fine-grained reactive access to nested objects and
lists. Each path through the store is backed by its own
[`Signal`][wybthon.Signal], so reading `store.user.name` only
subscribes the current computation to that specific leaf, not to the
entire store.

Writes are **draft-first**: the setter hands you a mutable draft of the
state and you mutate it directly with normal Python. There is no path
syntax and no `produce` wrapper; mutating the draft is just how stores
work.

Public surface:

- [`create_store`][wybthon.create_store]: build a store from an initial
  value; returns `(store, set_store)`.
- [`create_projection`][wybthon.create_projection]: a read-only store
  derived from reactive sources, updated fine-grained.
- [`create_optimistic_store`][wybthon.create_optimistic_store]: a store
  whose writes revert when in-flight [`action`][wybthon.action]s settle.
- [`reconcile`][wybthon.reconcile]: diff external data into a store,
  preserving object identity for unchanged items.
- [`unwrap`][wybthon.unwrap]: read the raw (non-reactive) data behind
  a store proxy.

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
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar

from .reactivity import (
    Signal,
    _register_optimistic_revert,
    create_render_effect,
    untrack,
)

__all__ = [
    "create_store",
    "create_projection",
    "create_optimistic_store",
    "reconcile",
    "unwrap",
]

T = TypeVar("T")


class _StoreNode:
    """Internal node holding one [`Signal`][wybthon.Signal] per property.

    Child nodes are cached by key so that proxy reads and draft writes
    for the same path always resolve to the same `Signal` instances.
    """

    __slots__ = ("_signals", "_raw", "_children", "_proxy", "_draft_proxy")

    def __init__(self, raw: Any) -> None:
        """Wrap `raw` in an empty signal/child cache."""
        object.__setattr__(self, "_signals", {})
        object.__setattr__(self, "_raw", raw)
        object.__setattr__(self, "_children", {})
        object.__setattr__(self, "_proxy", None)
        object.__setattr__(self, "_draft_proxy", None)

    def _get_signal(self, key: Any) -> Signal:
        signals: Dict[Any, Signal] = object.__getattribute__(self, "_signals")
        if key not in signals:
            raw = object.__getattribute__(self, "_raw")
            if isinstance(raw, dict):
                value = raw.get(key)
            elif isinstance(raw, (list, tuple)):
                try:
                    value = raw[key]
                except (IndexError, TypeError):
                    value = None
            else:
                value = getattr(raw, key, None)
            signals[key] = Signal(value)
        return signals[key]

    def _get_child(self, key: Any) -> "_StoreNode":
        """Return (or create) a cached child node for `key`."""
        children: Dict[Any, _StoreNode] = object.__getattribute__(self, "_children")
        if key not in children:
            raw = object.__getattribute__(self, "_raw")
            if isinstance(raw, dict):
                child_raw = raw.get(key)
            elif isinstance(raw, (list, tuple)):
                try:
                    child_raw = raw[key]
                except (IndexError, TypeError):
                    child_raw = None
            else:
                child_raw = getattr(raw, key, None)
            child_node = _StoreNode(child_raw)
            children[key] = child_node
        return children[key]

    def _set_value(self, key: Any, value: Any) -> None:
        raw = object.__getattribute__(self, "_raw")
        signals: Dict[Any, Signal] = object.__getattribute__(self, "_signals")
        children: Dict[Any, _StoreNode] = object.__getattribute__(self, "_children")

        if isinstance(raw, dict):
            raw[key] = value
        elif isinstance(raw, list):
            raw[key] = value
        else:
            setattr(raw, key, value)

        if key in signals:
            signals[key].set(value)
        else:
            signals[key] = Signal(value)

        if key in children:
            child_node = children[key]
            if isinstance(value, (dict, list)):
                child_node._replace_raw(value)
            else:
                children.pop(key, None)

    def _replace_raw(self, new_raw: Any) -> None:
        """Replace the underlying raw data and update all affected signals."""
        signals: Dict[Any, Signal] = object.__getattribute__(self, "_signals")
        children: Dict[Any, _StoreNode] = object.__getattribute__(self, "_children")
        object.__setattr__(self, "_raw", new_raw)

        if isinstance(new_raw, dict):
            keys = set(new_raw.keys()) | set(signals.keys())
        elif isinstance(new_raw, (list, tuple)):
            keys = set(range(len(new_raw))) | set(k for k in signals if isinstance(k, int))
        else:
            keys = set(signals.keys())

        for key in keys:
            if isinstance(new_raw, dict):
                new_val = new_raw.get(key)
            elif isinstance(new_raw, (list, tuple)):
                try:
                    new_val = new_raw[key]
                except (IndexError, TypeError):
                    new_val = None
            else:
                new_val = getattr(new_raw, key, None)

            if key in signals:
                signals[key].set(new_val)

            if key in children:
                if isinstance(new_val, (dict, list)):
                    children[key]._replace_raw(new_val)
                else:
                    children.pop(key, None)

        if isinstance(new_raw, (list, tuple)) and "length" in signals:
            signals["length"].set(len(new_raw))


def _wrap_value(value: Any, node: _StoreNode, *, draft: bool = False) -> Any:
    """Wrap a raw value in a reactive proxy backed by `node`.

    Read proxies and draft proxies are cached separately per node so
    repeated reads of the same path return the same proxy object
    (stable identity).
    """
    if isinstance(value, (dict, list)):
        cache_attr = "_draft_proxy" if draft else "_proxy"
        cached = object.__getattribute__(node, cache_attr)
        expected: type
        if isinstance(value, dict):
            expected = _DraftProxy if draft else _StoreProxy
        else:
            expected = _DraftListProxy if draft else _StoreListProxy
        if type(cached) is expected:
            return cached
        proxy: Any = expected(node)
        object.__setattr__(node, cache_attr, proxy)
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
        """Bind this proxy to its backing `_StoreNode`."""
        object.__setattr__(self, "_node", node)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            return object.__getattribute__(self, name)
        node: _StoreNode = object.__getattribute__(self, "_node")
        sig = node._get_signal(name)
        val = sig.get()
        if isinstance(val, (dict, list)):
            child_node = node._get_child(name)
            object.__setattr__(child_node, "_raw", val)
            return _wrap_value(val, child_node)
        return val

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            return self.__getattr__(key)
        node: _StoreNode = object.__getattribute__(self, "_node")
        sig = node._get_signal(key)
        val = sig.get()
        if isinstance(val, (dict, list)):
            child_node = node._get_child(key)
            object.__setattr__(child_node, "_raw", val)
            return _wrap_value(val, child_node)
        return val

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        raise AttributeError("Store is read-only. Mutate the draft inside set_store(lambda s: ...) instead.")

    def __repr__(self) -> str:
        node: _StoreNode = object.__getattribute__(self, "_node")
        raw = object.__getattribute__(node, "_raw")
        return f"Store({raw!r})"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, _StoreProxy):
            other_node: _StoreNode = object.__getattribute__(other, "_node")
            other_raw = object.__getattribute__(other_node, "_raw")
            node: _StoreNode = object.__getattribute__(self, "_node")
            raw = object.__getattribute__(node, "_raw")
            return raw == other_raw
        if isinstance(other, dict):
            node = object.__getattribute__(self, "_node")
            raw = object.__getattribute__(node, "_raw")
            return raw == other
        return NotImplemented

    def __contains__(self, key: Any) -> bool:
        node: _StoreNode = object.__getattribute__(self, "_node")
        raw = object.__getattribute__(node, "_raw")
        return key in raw

    def __iter__(self):
        node: _StoreNode = object.__getattribute__(self, "_node")
        raw = object.__getattribute__(node, "_raw")
        return iter(raw)

    def __len__(self) -> int:
        node: _StoreNode = object.__getattribute__(self, "_node")
        raw = object.__getattribute__(node, "_raw")
        return len(raw)


class _StoreListProxy:
    """Reactive read proxy for list-like store values.

    Index reads track the corresponding `Signal`. Supports `len()`,
    iteration, and `in` checks; mutations must go through the store
    setter's draft.
    """

    __slots__ = ("_node",)

    def __init__(self, node: _StoreNode) -> None:
        """Bind this proxy to its backing `_StoreNode`."""
        object.__setattr__(self, "_node", node)

    def __getitem__(self, index: int) -> Any:
        node: _StoreNode = object.__getattribute__(self, "_node")
        sig = node._get_signal(index)
        val = sig.get()
        if isinstance(val, (dict, list)):
            child_node = node._get_child(index)
            object.__setattr__(child_node, "_raw", val)
            return _wrap_value(val, child_node)
        return val

    def __len__(self) -> int:
        node: _StoreNode = object.__getattribute__(self, "_node")
        raw: list = object.__getattribute__(node, "_raw")
        length_sig = node._get_signal("length")
        length_sig.get()
        return len(raw)

    def __iter__(self):
        node: _StoreNode = object.__getattribute__(self, "_node")
        raw: list = object.__getattribute__(node, "_raw")
        length_sig = node._get_signal("length")
        length_sig.get()
        for i in range(len(raw)):
            yield self[i]

    def __contains__(self, item: Any) -> bool:
        node: _StoreNode = object.__getattribute__(self, "_node")
        raw: list = object.__getattribute__(node, "_raw")
        return item in raw

    def __repr__(self) -> str:
        node: _StoreNode = object.__getattribute__(self, "_node")
        raw = object.__getattribute__(node, "_raw")
        return f"StoreList({raw!r})"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, _StoreListProxy):
            other_node: _StoreNode = object.__getattribute__(other, "_node")
            other_raw = object.__getattribute__(other_node, "_raw")
            node: _StoreNode = object.__getattribute__(self, "_node")
            raw = object.__getattribute__(node, "_raw")
            return raw == other_raw
        if isinstance(other, list):
            node = object.__getattribute__(self, "_node")
            raw = object.__getattribute__(node, "_raw")
            return raw == other
        return NotImplemented


# --------------- draft proxies (handed to set_store callbacks) ---------------


class _DraftProxy(_StoreProxy):
    """Writable draft over a dict store node.

    Handed to `set_store(fn)` callbacks. Reads behave like the read
    proxy (nested containers wrap in nested drafts); writes apply
    immediately to the underlying raw data and notify exactly the
    affected leaf signals. Because effects flush once per scheduled
    flush, a draft function making many writes still produces a single
    settled update.
    """

    __slots__ = ()

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            return object.__getattribute__(self, name)
        node: _StoreNode = object.__getattribute__(self, "_node")
        sig = node._get_signal(name)
        val = sig.get()
        if isinstance(val, (dict, list)):
            child_node = node._get_child(name)
            object.__setattr__(child_node, "_raw", val)
            return _wrap_value(val, child_node, draft=True)
        return val

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            return self.__getattr__(key)
        node: _StoreNode = object.__getattribute__(self, "_node")
        sig = node._get_signal(key)
        val = sig.get()
        if isinstance(val, (dict, list)):
            child_node = node._get_child(key)
            object.__setattr__(child_node, "_raw", val)
            return _wrap_value(val, child_node, draft=True)
        return val

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        node: _StoreNode = object.__getattribute__(self, "_node")
        node._set_value(name, value)

    def __setitem__(self, key: Any, value: Any) -> None:
        node: _StoreNode = object.__getattribute__(self, "_node")
        node._set_value(key, value)

    def __delitem__(self, key: Any) -> None:
        node: _StoreNode = object.__getattribute__(self, "_node")
        raw = object.__getattribute__(node, "_raw")
        if isinstance(raw, dict):
            raw.pop(key, None)
            node._replace_raw(raw)
        elif isinstance(raw, list):
            raw.pop(key)
            node._replace_raw(raw)

    def update(self, values: Dict[str, Any]) -> None:
        """Merge `values` into this draft (dict-style bulk write)."""
        node: _StoreNode = object.__getattribute__(self, "_node")
        for k, v in values.items():
            node._set_value(k, v)


class _DraftListProxy(_StoreListProxy):
    """Writable draft over a list store node.

    Supports index assignment plus `append`, `insert`, `pop`, `remove`,
    `extend`, and `clear`, notifying index and length subscribers.
    """

    __slots__ = ()

    def _raw_list(self) -> list:
        node: _StoreNode = object.__getattribute__(self, "_node")
        return object.__getattribute__(node, "_raw")

    def __getitem__(self, index: int) -> Any:
        node: _StoreNode = object.__getattribute__(self, "_node")
        sig = node._get_signal(index)
        val = sig.get()
        if isinstance(val, (dict, list)):
            child_node = node._get_child(index)
            object.__setattr__(child_node, "_raw", val)
            return _wrap_value(val, child_node, draft=True)
        return val

    def __setitem__(self, index: Any, value: Any) -> None:
        node: _StoreNode = object.__getattribute__(self, "_node")
        node._set_value(index, value)

    def __delitem__(self, index: Any) -> None:
        node: _StoreNode = object.__getattribute__(self, "_node")
        raw = self._raw_list()
        raw.pop(index)
        node._replace_raw(raw)

    def append(self, value: Any) -> None:
        """Append `value`, notifying index and length subscribers."""
        node: _StoreNode = object.__getattribute__(self, "_node")
        raw = self._raw_list()
        raw.append(value)
        node._replace_raw(raw)

    def extend(self, values: Any) -> None:
        """Append every item in `values`."""
        node: _StoreNode = object.__getattribute__(self, "_node")
        raw = self._raw_list()
        raw.extend(values)
        node._replace_raw(raw)

    def insert(self, index: int, value: Any) -> None:
        """Insert `value` at `index`, shifting later items."""
        node: _StoreNode = object.__getattribute__(self, "_node")
        raw = self._raw_list()
        raw.insert(index, value)
        node._replace_raw(raw)

    def pop(self, index: int = -1) -> Any:
        """Remove and return the item at `index` (default: last)."""
        node: _StoreNode = object.__getattribute__(self, "_node")
        raw = self._raw_list()
        value = raw.pop(index)
        node._replace_raw(raw)
        return value

    def remove(self, value: Any) -> None:
        """Remove the first occurrence of `value`."""
        node: _StoreNode = object.__getattribute__(self, "_node")
        raw = self._raw_list()
        raw.remove(value)
        node._replace_raw(raw)

    def clear(self) -> None:
        """Remove every item."""
        node: _StoreNode = object.__getattribute__(self, "_node")
        raw = self._raw_list()
        raw.clear()
        node._replace_raw(raw)


def _make_draft(node: _StoreNode) -> Any:
    raw = object.__getattribute__(node, "_raw")
    if isinstance(raw, dict):
        return _wrap_value(raw, node, draft=True)
    if isinstance(raw, list):
        return _wrap_value(raw, node, draft=True)
    return raw


class _StoreSetter:
    """Callable that applies draft mutations to a store.

    Two calling conventions, matching SolidJS 2.0 `setStore`:

    - `set_store(fn)`: `fn` receives a mutable **draft** of the state;
      mutate it with normal Python (attribute and index assignment,
      list methods). Only the leaf signals whose values actually
      changed notify.
    - `set_store(reconcile(data))`: merge external data in, preserving
      object identity for unchanged items (see
      [`reconcile`][wybthon.reconcile]).
    """

    def __init__(self, node: _StoreNode) -> None:
        """Bind this setter to the store's root node."""
        self._node = node

    def __call__(self, modifier: Any) -> None:
        if isinstance(modifier, _ReconcileResult):
            modifier._apply(self._node)
            return
        if callable(modifier):
            modifier(_make_draft(self._node))
            return
        raise TypeError("set_store() takes a draft function or a reconcile() result")


def create_store(initial: Any) -> Tuple[Any, _StoreSetter]:
    """Create a reactive store from an initial value.

    Args:
        initial: Initial state. Dicts and lists are wrapped in
            reactive proxies; other values are returned unchanged.

    Returns:
        A tuple `(store, set_store)` where `store` is a read-only
        reactive proxy that tracks reads per-path, and `set_store`
        applies **draft mutations**: call it with a function that
        receives a mutable draft, or with a
        [`reconcile`][wybthon.reconcile] result.

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
        ```
    """
    node = _StoreNode(initial)
    if isinstance(initial, dict):
        proxy: Any = _StoreProxy(node)
    elif isinstance(initial, list):
        proxy = _StoreListProxy(node)
    else:
        proxy = initial
    setter = _StoreSetter(node)
    return proxy, setter


# --------------- projections ---------------


def create_projection(fn: Callable[[Any], Any], initial: Optional[Any] = None) -> Any:
    """Create a read-only store derived from reactive sources.

    `fn` receives a mutable draft of the projection's state and runs
    inside a render-phase computation: any signals, memos, or other
    stores it reads become dependencies, and when they change `fn`
    re-runs against the same draft. Because writes go through
    fine-grained store signals, consumers re-render only for the paths
    that actually changed.

    Matches SolidJS 2.0's `createProjection`.

    Args:
        fn: Draft mutator. Reads are tracked; mutate the draft to
            publish derived state.
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
    state = initial if initial is not None else {}
    node = _StoreNode(state)
    draft = _make_draft(node)

    create_render_effect(lambda: fn(draft))

    if isinstance(state, dict):
        return _StoreProxy(node)
    if isinstance(state, list):
        return _StoreListProxy(node)
    return state


# --------------- optimistic stores ---------------


def create_optimistic_store(source: Any, initial: Optional[Any] = None) -> Tuple[Any, Callable[[Any], None]]:
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

        shown, set_shown = create_optimistic_store(lambda: unwrap(todos)["items"], [])

        @action
        async def add(title):
            set_shown(lambda s: s.append({"title": title, "saving": True}))
            saved = await api_create(title)
            set_todos(lambda s: s.items.append(saved))
        ```
    """
    derived = callable(source)
    if derived:
        state: Any = initial if initial is not None else {}
    else:
        state = source
    node = _StoreNode(state)
    draft = _make_draft(node)

    base_snapshot: Dict[str, Any] = {"value": copy.deepcopy(unwrap_raw(state))}

    def _reconcile_to(data: Any) -> None:
        merged = _merge_data(object.__getattribute__(node, "_raw"), copy.deepcopy(data), "id")
        node._replace_raw(merged)

    if derived:

        def _track_base() -> None:
            data = source()
            base_snapshot["value"] = copy.deepcopy(unwrap_raw(data))
            _reconcile_to(base_snapshot["value"])

        create_render_effect(_track_base)

    def _revert() -> None:
        _reconcile_to(base_snapshot["value"])

    def set_optimistic(modifier: Any) -> None:
        if isinstance(modifier, _ReconcileResult):
            modifier._apply(node)
        elif callable(modifier):
            modifier(draft)
        else:
            raise TypeError("set_optimistic() takes a draft function or a reconcile() result")
        _register_optimistic_revert(lambda: untrack(_revert))

    if isinstance(state, dict):
        proxy: Any = _StoreProxy(node)
    elif isinstance(state, list):
        proxy = _StoreListProxy(node)
    else:
        proxy = state
    return proxy, set_optimistic


# --------------- reconcile / unwrap ---------------


def _merge_data(old: Any, new: Any, key: Optional[str]) -> Any:
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
            by_key: Dict[Any, Any] = {}
            for item in old:
                if isinstance(item, dict) and key in item:
                    by_key.setdefault(item[key], item)
            merged: list = []
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

    def __init__(self, data: Any, key: Optional[str]) -> None:
        """Capture the incoming data and list-matching key."""
        self._data = data
        self._key = key

    def _apply(self, node: _StoreNode) -> None:
        old_raw = object.__getattribute__(node, "_raw")
        merged = _merge_data(old_raw, self._data, self._key)
        node._replace_raw(merged)


def reconcile(data: Any, key: Optional[str] = "id") -> _ReconcileResult:
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


def unwrap_raw(value: Any) -> Any:
    """Internal: return the raw data behind a proxy, or `value` unchanged."""
    if isinstance(value, (_StoreProxy, _StoreListProxy)):
        node: _StoreNode = object.__getattribute__(value, "_node")
        return object.__getattribute__(node, "_raw")
    return value


def unwrap(value: Any) -> Any:
    """Return the raw data behind a store proxy (non-reactive).

    Matches SolidJS's `unwrap`. Reading the result doesn't subscribe
    to anything; mutations to it bypass reactivity entirely.

    Args:
        value: A store proxy (or any value).

    Returns:
        The underlying dict/list for proxies; `value` unchanged
        otherwise.
    """
    return unwrap_raw(value)
