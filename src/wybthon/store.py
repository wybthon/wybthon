"""Reactive stores for nested state management, inspired by SolidJS createStore.

Stores provide fine-grained reactive access to nested objects and lists.
Each path through the store is backed by its own ``Signal``, so reading
``store.user.name`` only subscribes the current computation to that
specific leaf — not the entire store.

Usage::

    from wybthon import create_store, produce

    store, set_store = create_store({
        "count": 0,
        "user": {"name": "Ada", "age": 30},
        "todos": [
            {"id": 1, "text": "Learn Wybthon", "done": False},
        ],
    })

    # Reading (reactive):
    store.count           # 0
    store.user.name       # "Ada"
    store.todos[0].text   # "Learn Wybthon"

    # Writing via path-based setter:
    set_store("count", 5)
    set_store("user", "name", "Jane")
    set_store("count", lambda c: c + 1)
    set_store("todos", 0, "done", True)

    # Writing via produce (batch mutations):
    set_store(produce(lambda s: setattr(s, "count", s.count + 1)))
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Sequence, Tuple, TypeVar

from .reactivity import Signal

__all__ = ["create_store", "produce"]

T = TypeVar("T")


class _StoreNode:
    """Internal node that holds a Signal per property and caches child nodes.

    Child nodes are cached by key so that proxy reads and setter writes
    for the same path always resolve to the same ``Signal`` instances.
    """

    __slots__ = ("_signals", "_raw", "_children")

    def __init__(self, raw: Any) -> None:
        object.__setattr__(self, "_signals", {})
        object.__setattr__(self, "_raw", raw)
        object.__setattr__(self, "_children", {})

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
        """Return (or create) a cached child node for *key*."""
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


def _wrap_value(value: Any, node: _StoreNode) -> Any:
    """Wrap a raw value in a reactive proxy backed by *node*."""
    if isinstance(value, (dict, list)):
        if isinstance(value, dict):
            return _StoreProxy(node)
        return _StoreListProxy(node)
    return value


class _StoreProxy:
    """Reactive proxy for dict-like store objects.

    Attribute reads track the corresponding Signal; nested dicts/lists
    are lazily wrapped in their own proxies via cached child nodes.
    """

    __slots__ = ("_node",)

    def __init__(self, node: _StoreNode) -> None:
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

    Index reads track the corresponding Signal.  Supports ``len()``,
    iteration, and ``in`` checks.
    """

    __slots__ = ("_node",)

    def __init__(self, node: _StoreNode) -> None:
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
    """Walk a store tree following *path*, returning (parent_node, final_key).

    Uses the child-node cache so that writes resolve to the same nodes
    (and therefore the same Signals) as proxy reads.
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

    Supports several calling conventions mirroring SolidJS ``setStore``:

    - ``set_store("key", value)`` — set a top-level key
    - ``set_store("key", fn)`` — functional update (fn receives current value)
    - ``set_store("a", "b", value)`` — nested path
    - ``set_store("a", 0, "done", True)`` — path with list index
    - ``set_store(produce(fn))`` — batch mutations via produce
    """

    def __init__(self, node: _StoreNode) -> None:
        self._node = node

    def __call__(self, *args: Any) -> None:
        if len(args) == 0:
            raise TypeError("set_store() requires at least one argument")

        if len(args) == 1:
            arg = args[0]
            if isinstance(arg, _ProduceResult):
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

    Returns ``(store, set_store)`` where *store* is a reactive proxy that
    tracks reads per-path, and *set_store* is a setter supporting
    path-based updates.

    Example::

        store, set_store = create_store({"count": 0, "user": {"name": "Ada"}})

        # Reactive reads:
        store.count         # 0
        store.user.name     # "Ada"

        # Path-based writes:
        set_store("count", 5)
        set_store("user", "name", "Jane")
        set_store("count", lambda c: c + 1)

    See module docstring for full API documentation.
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
    """Mutable draft that records attribute writes for later application."""

    __slots__ = ("_target", "_patches")

    def __init__(self, raw: Any) -> None:
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
    """Marker wrapping a produce function for the store setter to recognize."""

    __slots__ = ("_fn",)

    def __init__(self, fn: Callable[..., None]) -> None:
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


def produce(fn: Callable[..., None]) -> _ProduceResult:
    """Create a producer for batch-mutating store state.

    The function *fn* receives a mutable draft of the store.  Mutations
    on the draft are recorded and applied reactively when passed to
    ``set_store``::

        set_store(produce(lambda s: setattr(s, "count", s.count + 1)))

    The draft supports attribute access, item access, ``append``, and
    ``pop`` for lists::

        set_store(produce(lambda s: s.todos.append({"text": "New", "done": False})))

    """
    return _ProduceResult(fn)
