"""Reactive stores for nested state, inspired by SolidJS `createStore`.

Stores provide fine-grained reactive access to nested objects and
lists. Each path through the store is backed by its own
[`Signal`][wybthon.Signal], so reading `store.user.name` only
subscribes the current computation to that specific leaf, not to the
entire store.

Public surface:

- [`create_store`][wybthon.create_store]: build a store from any
  initial value.
- [`produce`][wybthon.produce]: batch mutations through a mutable
  draft.
- [`reconcile`][wybthon.reconcile]: diff external data into a store,
  preserving object identity for unchanged items.
- [`unwrap`][wybthon.unwrap]: read the raw (non-reactive) data behind
  a store proxy.
- [`create_mutable`][wybthon.create_mutable]: a directly-writable
  store proxy (no separate setter).

Example:
    ```python
    from wybthon import create_store, produce

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

    set_store("count", 5)
    set_store("user", "name", "Jane")
    set_store("count", lambda c: c + 1)
    set_store("todos", 0, "done", True)

    set_store(produce(lambda s: setattr(s, "count", s.count + 1)))
    ```

See Also:
    - [Reactivity guide](../concepts/reactivity.md)
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Sequence, Tuple, TypeVar

from .reactivity import Signal, batch

__all__ = ["create_store", "produce", "reconcile", "unwrap", "create_mutable", "modify_mutable"]

T = TypeVar("T")


class _StoreNode:
    """Internal node holding one [`Signal`][wybthon.Signal] per property.

    Child nodes are cached by key so that proxy reads and setter
    writes for the same path always resolve to the same `Signal`
    instances. The `_mutable` flag (set by `create_mutable`, inherited
    by children) controls whether wrapped values are writable proxies.
    """

    __slots__ = ("_signals", "_raw", "_children", "_proxy", "_mutable")

    def __init__(self, raw: Any, mutable: bool = False) -> None:
        """Wrap `raw` in an empty signal/child cache."""
        object.__setattr__(self, "_signals", {})
        object.__setattr__(self, "_raw", raw)
        object.__setattr__(self, "_children", {})
        object.__setattr__(self, "_proxy", None)
        object.__setattr__(self, "_mutable", mutable)

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
            child_node = _StoreNode(child_raw, object.__getattribute__(self, "_mutable"))
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


def _wrap_value(value: Any, node: _StoreNode) -> Any:
    """Wrap a raw value in a reactive proxy backed by `node`.

    Proxies are cached per node so repeated reads of the same path
    return the same proxy object (stable identity). Nodes belonging to
    a mutable store wrap in directly-writable proxy variants.
    """
    if isinstance(value, (dict, list)):
        cached = object.__getattribute__(node, "_proxy")
        mutable = object.__getattribute__(node, "_mutable")
        if isinstance(value, dict):
            if isinstance(cached, _StoreProxy):
                return cached
            proxy: Any = _MutableProxy(node) if mutable else _StoreProxy(node)
        else:
            if isinstance(cached, _StoreListProxy):
                return cached
            proxy = _MutableListProxy(node) if mutable else _StoreListProxy(node)
        object.__setattr__(node, "_proxy", proxy)
        return proxy
    return value


class _StoreProxy:
    """Reactive proxy for dict-like store objects.

    Attribute reads track the corresponding `Signal`; nested dicts and
    lists are lazily wrapped in their own proxies via cached child
    nodes.
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
        raise AttributeError("Store is read-only. Use set_store() to update values.")

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
    """Reactive proxy for list-like store values.

    Index reads track the corresponding `Signal`. Supports `len()`,
    iteration, and `in` checks; mutations must go through the store
    setter.
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


def _resolve_path(node: _StoreNode, path: Sequence[Any]) -> Tuple[_StoreNode, Any]:
    """Walk a store tree following `path`, returning `(parent_node, final_key)`.

    Uses the child-node cache so that writes resolve to the same
    nodes (and therefore the same signals) as proxy reads.

    Args:
        node: Root node of the store sub-tree.
        path: Sequence of attribute names or indices.

    Returns:
        A tuple `(parent_node, final_key)` where `parent_node` owns
        the leaf signal addressed by `final_key`.

    Raises:
        KeyError: If the path passes through a non-container value.
    """
    current = node
    for segment in path[:-1]:
        current = current._get_child(segment)
        raw = object.__getattribute__(current, "_raw")
        if not isinstance(raw, (dict, list)):
            raise KeyError(f"Cannot traverse into non-container at path segment {segment!r}")
    return current, path[-1]


class _StoreSetter:
    """Callable that applies path-based updates to a store.

    Supports several calling conventions mirroring SolidJS
    `setStore`:

    - `set_store("key", value)`: set a top-level key.
    - `set_store("key", fn)`: functional update (`fn(current)`).
    - `set_store("a", "b", value)`: nested path.
    - `set_store("a", 0, "done", True)`: path with list index.
    - `set_store(produce(fn))`: batch mutations via
      [`produce`][wybthon.produce].
    """

    def __init__(self, node: _StoreNode) -> None:
        """Bind this setter to the store's root node."""
        self._node = node

    def __call__(self, *args: Any) -> None:
        if len(args) == 0:
            raise TypeError("set_store() requires at least one argument")

        # All signal writes from a single ``set_store`` call are coalesced into
        # one flush so that a consumer reading several paths in one effect sees
        # a single, fully-settled update (glitch-free), matching SolidJS stores.
        with batch():
            self._apply(*args)

    def _apply(self, *args: Any) -> None:
        if len(args) == 1:
            arg = args[0]
            if isinstance(arg, _ProduceResult):
                arg._apply(self._node)
                return
            if isinstance(arg, _ReconcileResult):
                arg._apply(self._node)
                return
            if callable(arg):
                raw = object.__getattribute__(self._node, "_raw")
                new_raw = arg(raw)
                if new_raw is not raw and new_raw is not None:
                    self._node._replace_raw(new_raw)
                return
            if isinstance(arg, dict):
                for k, v in arg.items():
                    self._node._set_value(k, v)
                return
            raise TypeError("set_store() with a single argument requires a produce(), callable, or dict")

        *path_parts, final = args
        if not path_parts:
            raise TypeError("set_store() requires a path when called with two or more arguments")

        if isinstance(final, _ReconcileResult):
            if len(path_parts) == 1:
                target = self._node._get_child(path_parts[0])
            else:
                parent_node, last_key = _resolve_path(self._node, path_parts)
                target = parent_node._get_child(last_key)
            final._apply(target)
            # The parent's raw container holds a reference to the child's
            # raw value, which reconcile may have swapped out.
            if len(path_parts) == 1:
                self._node._set_value(path_parts[0], object.__getattribute__(target, "_raw"))
            else:
                parent_node._set_value(last_key, object.__getattribute__(target, "_raw"))
            return

        if len(path_parts) == 1:
            key = path_parts[0]
            if callable(final):
                sig = self._node._get_signal(key)
                old = sig._value
                new_val = final(old)
                self._node._set_value(key, new_val)
            else:
                self._node._set_value(key, final)
            self._update_length_if_list()
            return

        parent_node, last_key = _resolve_path(self._node, path_parts)
        if callable(final):
            sig = parent_node._get_signal(last_key)
            old = sig._value
            new_val = final(old)
            parent_node._set_value(last_key, new_val)
        else:
            parent_node._set_value(last_key, final)

    def _update_length_if_list(self) -> None:
        raw = object.__getattribute__(self._node, "_raw")
        if isinstance(raw, list):
            signals: Dict[Any, Signal] = object.__getattribute__(self._node, "_signals")
            if "length" in signals:
                signals["length"].set(len(raw))


def create_store(initial: Any) -> Tuple[Any, _StoreSetter]:
    """Create a reactive store from an initial value.

    Args:
        initial: Initial state. Dicts and lists are wrapped in
            reactive proxies; other values are returned unchanged.

    Returns:
        A tuple `(store, set_store)` where `store` is a reactive
        proxy that tracks reads per-path, and `set_store` is a setter
        supporting path-based updates and
        [`produce`][wybthon.produce] batches.

    Example:
        ```python
        store, set_store = create_store({"count": 0, "user": {"name": "Ada"}})

        store.count         # 0
        store.user.name     # "Ada"

        set_store("count", 5)
        set_store("user", "name", "Jane")
        set_store("count", lambda c: c + 1)
        ```

    See the module docstring for the full set of supported calling
    conventions.
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


# --------------- produce ---------------


class _ProduceDraft:
    """Mutable draft that records attribute writes for later application.

    Used internally by [`produce`][wybthon.produce]. Mutations made on
    the draft are accumulated as patches and replayed against the
    real store via [`_apply_patches`][wybthon.store._apply_patches].
    """

    __slots__ = ("_target", "_patches")

    def __init__(self, raw: Any) -> None:
        """Initialize the draft over `raw` with an empty patch list."""
        object.__setattr__(self, "_target", raw)
        object.__setattr__(self, "_patches", [])

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            return object.__getattribute__(self, name)
        target = object.__getattribute__(self, "_target")
        if isinstance(target, dict):
            val = target.get(name)
        else:
            val = getattr(target, name, None)
        if isinstance(val, (dict, list)):
            child = _ProduceDraft(val)
            patches: list = object.__getattribute__(self, "_patches")
            patches.append(("_child", name, child))
            return child
        return val

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        patches: list = object.__getattribute__(self, "_patches")
        patches.append(("set", name, value))

    def __getitem__(self, key: Any) -> Any:
        target = object.__getattribute__(self, "_target")
        val = target[key]
        if isinstance(val, (dict, list)):
            child = _ProduceDraft(val)
            patches: list = object.__getattribute__(self, "_patches")
            patches.append(("_child", key, child))
            return child
        return val

    def __setitem__(self, key: Any, value: Any) -> None:
        patches: list = object.__getattribute__(self, "_patches")
        patches.append(("set", key, value))

    def append(self, value: Any) -> None:
        patches: list = object.__getattribute__(self, "_patches")
        patches.append(("append", None, value))

    def pop(self, index: int = -1) -> Any:
        target = object.__getattribute__(self, "_target")
        val = target[index]
        patches: list = object.__getattribute__(self, "_patches")
        patches.append(("pop", index, None))
        return val


class _ProduceResult:
    """Marker wrapping a `produce` function for the store setter to recognize."""

    __slots__ = ("_fn",)

    def __init__(self, fn: Callable[..., None]) -> None:
        """Capture `fn` until the store setter applies it to a draft."""
        self._fn = fn

    def _apply(self, node: _StoreNode) -> None:
        raw = object.__getattribute__(node, "_raw")
        draft = _ProduceDraft(raw)
        self._fn(draft)
        _apply_patches(node, draft)


def _apply_patches(node: _StoreNode, draft: _ProduceDraft) -> None:
    """Recursively apply recorded patches from a produce draft to a store node."""
    patches: list = object.__getattribute__(draft, "_patches")
    raw = object.__getattribute__(node, "_raw")

    for op, key, value in patches:
        if op == "set":
            node._set_value(key, value)
        elif op == "append":
            if isinstance(raw, list):
                raw.append(value)
                signals: Dict[Any, Signal] = object.__getattribute__(node, "_signals")
                new_idx = len(raw) - 1
                signals[new_idx] = Signal(value)
                if "length" in signals:
                    signals["length"].set(len(raw))
        elif op == "pop":
            if isinstance(raw, list):
                raw.pop(key)
                node._replace_raw(raw)
        elif op == "_child":
            child_node = node._get_child(key)
            _apply_patches(child_node, value)


# --------------- reconcile / unwrap / create_mutable ---------------


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
        set_store("todos", reconcile(fetched_todos))
        ```
    """
    return _ReconcileResult(data, key)


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
    if isinstance(value, (_StoreProxy, _StoreListProxy, _MutableProxy)):
        node: _StoreNode = object.__getattribute__(value, "_node")
        return object.__getattribute__(node, "_raw")
    return value


class _MutableProxy(_StoreProxy):
    """Directly-writable variant of `_StoreProxy` used by `create_mutable`."""

    __slots__ = ()

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        node: _StoreNode = object.__getattribute__(self, "_node")
        with batch():
            node._set_value(name, value)

    def __setitem__(self, key: Any, value: Any) -> None:
        node: _StoreNode = object.__getattribute__(self, "_node")
        with batch():
            node._set_value(key, value)


class _MutableListProxy(_StoreListProxy):
    """Directly-writable variant of `_StoreListProxy` used by `create_mutable`."""

    __slots__ = ()

    def _raw_list(self) -> list:
        node: _StoreNode = object.__getattribute__(self, "_node")
        return object.__getattribute__(node, "_raw")

    def __setitem__(self, index: Any, value: Any) -> None:
        node: _StoreNode = object.__getattribute__(self, "_node")
        with batch():
            node._set_value(index, value)

    def append(self, value: Any) -> None:
        """Append `value`, notifying index and length subscribers."""
        node: _StoreNode = object.__getattribute__(self, "_node")
        raw = self._raw_list()
        with batch():
            raw.append(value)
            node._replace_raw(raw)

    def insert(self, index: int, value: Any) -> None:
        """Insert `value` at `index`, shifting later items."""
        node: _StoreNode = object.__getattribute__(self, "_node")
        raw = self._raw_list()
        with batch():
            raw.insert(index, value)
            node._replace_raw(raw)

    def pop(self, index: int = -1) -> Any:
        """Remove and return the item at `index` (default: last)."""
        node: _StoreNode = object.__getattribute__(self, "_node")
        raw = self._raw_list()
        with batch():
            value = raw.pop(index)
            node._replace_raw(raw)
        return value

    def remove(self, value: Any) -> None:
        """Remove the first occurrence of `value`."""
        node: _StoreNode = object.__getattribute__(self, "_node")
        raw = self._raw_list()
        with batch():
            raw.remove(value)
            node._replace_raw(raw)

    def clear(self) -> None:
        """Remove every item."""
        node: _StoreNode = object.__getattribute__(self, "_node")
        raw = self._raw_list()
        with batch():
            raw.clear()
            node._replace_raw(raw)


def create_mutable(initial: Any) -> Any:
    """Create a directly-writable reactive store proxy.

    Matches SolidJS's `createMutable`: reads are tracked per path like
    [`create_store`][wybthon.create_store], and writes go through plain
    attribute or item assignment at **any depth**. Nested dicts wrap in
    writable proxies, and nested lists support `append`, `insert`,
    `pop`, `remove`, `clear`, and index assignment. Each write batches
    its notifications; use [`modify_mutable`][wybthon.modify_mutable]
    with [`produce`][wybthon.produce] or
    [`reconcile`][wybthon.reconcile] to group several changes into one
    update.

    Args:
        initial: Initial dict state.

    Returns:
        A mutable reactive proxy.

    Example:
        ```python
        state = create_mutable({"count": 0, "user": {"name": "Ada"}, "tags": []})
        create_effect(lambda: print(state.count, state.user.name))
        state.count = 5             # effect re-runs
        state.user.name = "Grace"   # nested write, effect re-runs
        state.tags.append("new")    # list mutation, tracked
        ```
    """
    if not isinstance(initial, dict):
        raise TypeError("create_mutable() requires a dict initial value")
    node = _StoreNode(initial, mutable=True)
    proxy = _MutableProxy(node)
    object.__setattr__(node, "_proxy", proxy)
    return proxy


def modify_mutable(state: Any, modifier: Any) -> None:
    """Apply a batched modification to a [`create_mutable`][wybthon.create_mutable] proxy.

    Matches SolidJS's `modifyMutable`. The modifier is either a
    [`produce`][wybthon.produce] draft function, a
    [`reconcile`][wybthon.reconcile] result, or a plain callable
    receiving a mutable draft (shorthand for `produce`). All resulting
    signal notifications flush once, as a single update.

    Args:
        state: A proxy created by `create_mutable` (or any store
            proxy).
        modifier: A `produce(...)` / `reconcile(...)` result, or a
            callable draft mutator.

    Example:
        ```python
        state = create_mutable({"a": 1, "b": 2})
        modify_mutable(state, produce(lambda s: (
            setattr(s, "a", 10),
            setattr(s, "b", 20),
        )))
        modify_mutable(state, reconcile(fetched_state))
        ```
    """
    if not isinstance(state, (_StoreProxy, _StoreListProxy)):
        raise TypeError("modify_mutable() requires a store proxy")
    node: _StoreNode = object.__getattribute__(state, "_node")
    if callable(modifier) and not isinstance(modifier, (_ProduceResult, _ReconcileResult)):
        modifier = _ProduceResult(modifier)
    if not isinstance(modifier, (_ProduceResult, _ReconcileResult)):
        raise TypeError("modify_mutable() requires a produce(), reconcile(), or callable modifier")
    with batch():
        modifier._apply(node)


def produce(fn: Callable[..., None]) -> _ProduceResult:
    """Create a producer for batch-mutating store state.

    `fn` receives a mutable draft of the store. Mutations are
    recorded and applied reactively when the producer is passed to a
    store setter created by [`create_store`][wybthon.create_store].

    The draft supports attribute access, item access, and `append` /
    `pop` for lists.

    Args:
        fn: A function that mutates the supplied draft. The draft is
            consumed immediately when applied; don't keep a
            reference past the call.

    Returns:
        A marker object recognized by the store setter.

    Example:
        ```python
        set_store(produce(lambda s: setattr(s, "count", s.count + 1)))

        set_store(produce(lambda s: s.todos.append(
            {"text": "New", "done": False}
        )))
        ```
    """
    return _ProduceResult(fn)
