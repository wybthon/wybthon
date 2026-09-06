"""Component props: the `Props` container, `prop()` defaults, `merge`, and `omit`.

A component receives its props as a [`Props`][wybthon.Props] mapping of
name to [`Prop`][wybthon.Prop] accessor. `@component` unpacks that
mapping into the function's parameters; a plain function component
receives the mapping itself. Either way there is one access pattern:
call the accessor.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from ._core import Accessor, Prop, Signal, _unwrap, untrack

__all__ = ["Props", "prop", "merge", "omit"]

_MISSING = object()
_NO_DEFAULTS: Mapping[str, Any] = {}


class _DefaultProp[T](Prop[T]):
    """A `Prop` standing in for a component parameter's default value.

    Created by [`prop`][wybthon.prop]. When the component is mounted the
    reconciler replaces it with a live `Prop` bound to the parent's
    value (falling back to this default); when the component function is
    called directly, it behaves as a constant accessor.
    """

    __slots__ = ("default",)

    def __init__(self, default: T) -> None:
        super().__init__(Signal(default), "<default>")
        self.default = default

    def __call__(self) -> T:
        return self.default

    def peek(self) -> T:
        return self.default

    def __repr__(self) -> str:
        return f"prop({self.default!r})"


def prop[T](default: T) -> Prop[T]:
    """Declare a component parameter default with a `Prop[T]` type.

    Component parameters are accessors, so a plain default (`count=0`)
    is a type mismatch against `count: Prop[int]`. `prop(0)` gives the
    parameter the right type while recording the default the reconciler
    should use when the parent omits the prop.

    ```python
    @component
    def Greeting(name: Prop[str] = prop("world"), excited: Prop[bool] = prop(False)):
        return p("Hello, ", name, lambda: "!" if excited() else ".")
    ```

    Args:
        default: The value used when the parent doesn't pass the prop.

    Returns:
        A `Prop` marker carrying the default.
    """
    return _DefaultProp(default)


def default_value(value: Any) -> Any:
    """Return the raw default behind a `prop()` marker, or `value` itself."""
    if isinstance(value, _DefaultProp):
        return value.default
    return value


class Props(Mapping[str, Prop[Any]]):
    """Read-only mapping of prop name to [`Prop`][wybthon.Prop] accessor.

    Built by the reconciler for each mounted component. Both attribute
    and item access return the accessor for that name (creating it on
    first use), so `props.name()` and `props["name"]()` read the current
    value. Names absent from the parent's props resolve to the
    component's declared default, or `None`.

    Iteration and `len()` cover the keys the parent passed; `in` also
    reports declared defaults.

    Example:
        ```python
        def Greeting(props: Props):
            return p("Hello, ", props.name)
        ```
    """

    __slots__ = ("_raw", "_defaults", "_signals", "_props")

    def __init__(self, raw: Mapping[str, Any], defaults: Mapping[str, Any] | None = None) -> None:
        self._raw: dict[str, Any] = dict(raw)
        # Read-only here, so the component's declared defaults are shared
        # by every instance rather than copied per mount.
        self._defaults: Mapping[str, Any] = defaults if defaults else _NO_DEFAULTS
        self._signals: dict[str, Signal[Any]] = {}
        self._props: dict[str, Prop[Any]] = {}

    def _signal(self, key: str) -> Signal[Any]:
        sig = self._signals.get(key)
        if sig is None:
            value = self._raw.get(key, _MISSING)
            if value is _MISSING:
                value = self._defaults.get(key)
            sig = Signal(value, name=key)
            self._signals[key] = sig
        return sig

    def __getitem__(self, key: str) -> Prop[Any]:
        accessor = self._props.get(key)
        if accessor is None:
            accessor = Prop(self._signal(key), key)
            self._props[key] = accessor
        return accessor

    def __getattr__(self, name: str) -> Prop[Any]:
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self._raw)

    def __len__(self) -> int:
        return len(self._raw)

    def __contains__(self, key: object) -> bool:
        return key in self._raw or key in self._defaults

    def get(self, key: str, default: Any = None) -> Any:
        """Return the accessor for `key` (always present; see `__getitem__`)."""
        return self[key]

    def raw(self, key: str) -> Any:
        """Return the value for `key` exactly as the parent passed it, untracked.

        A reactive expression is returned as is (not called). Use this
        when a prop is a callback or an accessor you intend to hand on
        rather than read.
        """
        value = self._raw.get(key, _MISSING)
        if value is _MISSING:
            value = self._defaults.get(key)
        return value

    def snapshot(self) -> dict[str, Any]:
        """Return the current unwrapped values as a plain dict (untracked)."""
        keys = list(self._raw)
        for key in self._defaults:
            if key not in self._raw:
                keys.append(key)
        return {k: self[k].peek() for k in keys}

    def _update(self, new_raw: Mapping[str, Any]) -> None:
        """Push new parent props into the live signals (reconciler patch path)."""
        self._raw = dict(new_raw)
        for key, sig in self._signals.items():
            value = self._raw.get(key, _MISSING)
            if value is _MISSING:
                value = self._defaults.get(key)
            sig._set(value)

    def __repr__(self) -> str:
        return f"Props({self._raw!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Props):
            return self._raw == other._raw
        return NotImplemented

    def __hash__(self) -> int:
        return id(self)


# ---------------------------------------------------------------------------
# merge / omit
# ---------------------------------------------------------------------------


def _lookup(source: Any, key: str) -> Any:
    """Return `(found, value)` for `key` in a prop source (tracked read)."""
    if isinstance(source, Accessor):
        source = source()
    elif callable(source) and not isinstance(source, Mapping):
        source = source()
    if source is None:
        return False, None
    if isinstance(source, Props):
        if key in source:
            return True, source[key]()
        return False, None
    if isinstance(source, Mapping):
        if key in source:
            return True, _unwrap(source[key])
        return False, None
    return False, None


def _keys(source: Any) -> list[str]:
    if isinstance(source, Accessor):
        source = source()
    elif callable(source) and not isinstance(source, Mapping):
        source = source()
    if source is None:
        return []
    if isinstance(source, Props):
        keys = list(source)
        for key in source._defaults:
            if key not in source._raw:
                keys.append(key)
        return keys
    if isinstance(source, Mapping):
        return list(source)
    return []


class _KeyAccessor(Accessor[Any]):
    """Accessor for one key of a merged / omitted props view."""

    __slots__ = ("_view", "_key")

    def __init__(self, view: _PropsView, key: str) -> None:
        self._view = view
        self._key = key

    def __call__(self) -> Any:
        return self._view._resolve(self._key)

    def peek(self) -> Any:
        return untrack(lambda: self._view._resolve(self._key))

    def _label(self) -> str:
        return f"prop {self._key!r}"


class _PropsView(Mapping[str, Accessor[Any]]):
    """Base for the read-only reactive mappings returned by `merge` and `omit`."""

    __slots__ = ("_accessors",)

    def __init__(self) -> None:
        self._accessors: dict[str, _KeyAccessor] = {}

    def _resolve(self, key: str) -> Any:
        raise NotImplementedError

    def _all_keys(self) -> list[str]:
        raise NotImplementedError

    def __getitem__(self, key: str) -> Accessor[Any]:
        acc = self._accessors.get(key)
        if acc is None:
            acc = _KeyAccessor(self, key)
            self._accessors[key] = acc
        return acc

    def __getattr__(self, name: str) -> Accessor[Any]:
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self._all_keys())

    def __len__(self) -> int:
        return len(self._all_keys())

    def __contains__(self, key: object) -> bool:
        return key in self._all_keys()

    def snapshot(self) -> dict[str, Any]:
        """Return the current values as a plain dict (untracked)."""

        def resolve_all() -> dict[str, Any]:
            return {k: self._resolve(k) for k in self._all_keys()}

        return untrack(resolve_all)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.snapshot()!r})"


class _Merged(_PropsView):
    __slots__ = ("_sources",)

    def __init__(self, sources: tuple[Any, ...]) -> None:
        super().__init__()
        self._sources = sources

    def _resolve(self, key: str) -> Any:
        for source in reversed(self._sources):
            found, value = _lookup(source, key)
            if found:
                return value
        return None

    def _all_keys(self) -> list[str]:
        seen: dict[str, None] = {}
        for source in self._sources:
            for key in _keys(source):
                seen[key] = None
        return list(seen)


class _Omitted(_PropsView):
    __slots__ = ("_source", "_omit")

    def __init__(self, source: Any, omit_keys: frozenset[str]) -> None:
        super().__init__()
        self._source = source
        self._omit = omit_keys

    def _resolve(self, key: str) -> Any:
        if key in self._omit:
            return None
        _, value = _lookup(self._source, key)
        return value

    def _all_keys(self) -> list[str]:
        return [k for k in _keys(self._source) if k not in self._omit]

    def __contains__(self, key: object) -> bool:
        return key not in self._omit and key in _keys(self._source)


def merge(*sources: Any) -> Mapping[str, Accessor[Any]]:
    """Merge prop sources into one reactive mapping; later sources win.

    Each source may be a [`Props`][wybthon.Props] mapping, a plain dict
    (values may be accessors or static), a zero-arg function returning
    a dict, or another merged/omitted view. Reads resolve right-to-left
    at access time, so tracking flows through to whichever source
    supplied the key. A key present with the value `None` overrides
    earlier sources (`None` is a real value, not "skip").

    The result is a mapping of accessors: spread it onto an element
    (`button(**merge(defaults, rest))`) or pass it to a component.

    Example:
        ```python
        @component
        def Button(variant: Prop[str] = prop("solid"), **rest: Prop[Any]):
            attrs = merge({"type": "button"}, rest)
            return button(**attrs, class_=lambda: f"btn btn-{variant()}")
        ```
    """
    return _Merged(sources)


def omit(source: Any, *keys: str) -> Mapping[str, Accessor[Any]]:
    """Return a reactive view of `source` without the given keys.

    The replacement for `split_props`: keep the keys you handle locally
    as named parameters and forward the rest.

    ```python
    rest = omit(props, "class", "style")
    div(**rest)
    ```
    """
    return _Omitted(source, frozenset(keys))
