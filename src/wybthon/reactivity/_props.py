"""Component props: typed `Props` classes, `Prop[T]` fields, `prop()` defaults, `merge`, and `omit`.

A component declares its inputs on a subclass of [`Props`][wybthon.Props]
and takes one parameter annotated with that class:

```python
class GreetingProps(Props):
    name: Prop[str]
    excited: Prop[bool] = prop(default=False)
    on_wave: Callable[[], None] | None = None


@component
def Greeting(props: GreetingProps):
    return p("Hello, ", props.name, lambda: "!" if props.excited() else ".")
```

- A `Prop[T]` field is reactive. The parent may pass a value, an
  accessor, or a zero-argument function; reading `props.name` returns an
  [`Accessor`][wybthon.Accessor] that unwraps whichever it was.
- Any other field is plain data, returned as the parent passed it. A
  callback declared as a plain field is never called by the read.
- `Props` is a PEP 681 `dataclass_transform` base, so pyright and mypy
  check component calls without a plugin.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator, Mapping
from typing import Any, ClassVar, Self, dataclass_transform, overload

from ._core import _MISSING, Accessor, Signal, _PropAccessor, _unwrap, untrack

__all__ = ["Props", "ParentProps", "Prop", "prop", "merge", "omit"]


class _Default:
    """The marker `prop()` returns; replaced by the field's descriptor at class creation."""

    __slots__ = ("default", "factory")

    def __init__(self, default: Any, factory: Callable[[], Any] | None) -> None:
        self.default = default
        self.factory = factory


@overload
def prop[T](*, default: T) -> Prop[T]: ...
@overload
def prop[T](*, default_factory: Callable[[], T]) -> Prop[T]: ...
def prop(*, default: Any = _MISSING, default_factory: Callable[[], Any] | None = None) -> Any:
    """Declare a `Prop[T]` field's default.

    Type checkers only recognize a field specifier's default when it's
    passed by keyword, so write `prop(default=0)`. Use
    `default_factory` for mutable defaults.

    ```python
    class CounterProps(Props):
        step: Prop[int] = prop(default=1)
        tags: Prop[list[str]] = prop(default_factory=list)
    ```
    """
    if (default is _MISSING) == (default_factory is None):
        raise TypeError("prop() takes exactly one of default= or default_factory=")
    return _Default(default, default_factory)


class _Field:
    """Runtime metadata for one declared field."""

    __slots__ = ("name", "reactive", "default", "factory")

    def __init__(self, name: str, reactive: bool, default: Any, factory: Callable[[], Any] | None) -> None:
        self.name = name
        self.reactive = reactive
        self.default = default
        self.factory = factory

    @property
    def required(self) -> bool:
        return self.default is _MISSING and self.factory is None

    def initial(self) -> Any:
        if self.factory is not None:
            return self.factory()
        return None if self.default is _MISSING else self.default


class Prop[T]:
    """A reactive component input, declared on a [`Props`][wybthon.Props] class.

    The parent may pass a `T`, an accessor of `T`, or a zero-argument
    function returning `T`. Reading the field on the component's props
    returns an [`Accessor`][wybthon.Accessor]: place it in the tree to
    create a reactive hole, call it inside a tracking scope, or use
    `.peek()` for an intentional one-time read.
    """

    __slots__ = ("_field",)

    def __init__(self, field: _Field) -> None:
        self._field = field

    @overload
    def __get__(self, obj: None, owner: Any) -> Self: ...
    @overload
    def __get__(self, obj: object, owner: Any) -> Accessor[T]: ...
    def __get__(self, obj: Any, owner: Any) -> Any:
        if obj is None:
            return self
        return obj._wyb_accessor(self._field)

    def __set__(self, obj: object, value: T | Accessor[T] | Callable[[], T]) -> None:
        raise AttributeError("Component props are read-only")

    def __repr__(self) -> str:
        return f"Prop({self._field.name!r})"


class _Plain:
    """Descriptor for a plain (non-reactive) field: returns the parent's value as passed."""

    __slots__ = ("_field",)

    def __init__(self, field: _Field) -> None:
        self._field = field

    def __get__(self, obj: Any, owner: Any) -> Any:
        if obj is None:
            return self
        field = self._field
        value = obj._raw.get(field.name, _MISSING)
        return obj._wyb_default(field) if value is _MISSING else value

    def __set__(self, obj: object, value: Any) -> None:
        raise AttributeError("Component props are read-only")


_REACTIVE_ANNOTATION = re.compile(r"^(?:[\w.]+\.)?Prop(?:\[|$)")
_CLASSVAR_ANNOTATION = re.compile(r"^(?:[\w.]+\.)?ClassVar(?:\[|$)")


def _string_annotations(cls: type) -> dict[str, str]:
    import annotationlib

    return annotationlib.get_annotations(cls, format=annotationlib.Format.STRING)


@dataclass_transform(kw_only_default=True, frozen_default=True, field_specifiers=(prop,))
class _PropsBase:
    """Gives `Props` subclasses their checked keyword constructor (PEP 681)."""

    __slots__ = ()


class Props(_PropsBase):
    """Base class for a component's declared inputs.

    Subclass it, annotate fields, and take one parameter of that type in
    the component. Every component also accepts `key`, which gives the
    instance a stable identity for keyed reconciliation.

    At run time the reconciler builds one instance per mounted
    component. Reading a `Prop[T]` field returns an accessor that tracks
    the parent's current value, so a parent that later passes a new value
    (or an accessor) updates the child without re-running it.
    """

    __slots__ = ("_raw", "_sig", "_accessors", "_patchable", "_defaults")

    key: str | int | None = None

    _wyb_fields: ClassVar[dict[str, _Field]] = {}
    _wyb_required: ClassVar[frozenset[str]] = frozenset()
    _wyb_names: ClassVar[frozenset[str]] = frozenset({"key"})
    _wyb_reactive: ClassVar[tuple[str, ...]] = ()
    # Internal props classes (built-in components that forward attributes)
    # accept keys they don't declare.
    _wyb_open: ClassVar[bool] = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        fields = dict(getattr(cls, "_wyb_fields", {}))
        for name, annotation in _string_annotations(cls).items():
            if name.startswith("_") or _CLASSVAR_ANNOTATION.match(annotation):
                continue
            value = cls.__dict__.get(name, _MISSING)
            if isinstance(value, _Default):
                default, factory = value.default, value.factory
            elif isinstance(value, (Prop, _Plain)):
                continue
            else:
                default, factory = value, None
            reactive = bool(_REACTIVE_ANNOTATION.match(annotation))
            if not reactive and isinstance(value, _Default):
                raise TypeError(f"{cls.__qualname__}.{name}: prop() is for Prop[T] fields; use a plain default")
            field = _Field(name, reactive, default, factory)
            fields[name] = field
            setattr(cls, name, Prop(field) if reactive else _Plain(field))
        cls._wyb_fields = fields
        cls._wyb_required = frozenset(name for name, field in fields.items() if field.required)
        cls._wyb_names = frozenset(fields) | {"key"}
        cls._wyb_reactive = tuple(name for name, field in fields.items() if field.reactive)

    def __init__(self, **values: Any) -> None:
        self._raw: dict[str, Any] = values
        self._sig: Signal[dict[str, Any]] | None = None
        self._accessors: dict[str, Accessor[Any]] | None = None
        self._patchable = True
        self._defaults: dict[str, Any] | None = None

    @classmethod
    def _wyb_bind(cls, values: dict[str, Any], patchable: bool) -> Self:
        """The live instance a mounted component reads (reconciler internal)."""
        instance = cls.__new__(cls)
        instance._raw = values
        instance._sig = None
        instance._accessors = None
        instance._patchable = patchable
        instance._defaults = None
        return instance

    @classmethod
    def _wyb_check(cls, values: Mapping[str, Any], component: str) -> None:
        """Dev-mode validation of the keywords a component was called with."""
        if not cls._wyb_open:
            unknown = values.keys() - cls._wyb_names
            if unknown:
                raise TypeError(f"{component}() got unexpected prop(s): {', '.join(sorted(unknown))}")
        missing = cls._wyb_required - values.keys()
        if missing:
            raise TypeError(f"{component}() is missing required prop(s): {', '.join(sorted(missing))}")

    def _wyb_signal(self) -> Signal[dict[str, Any]]:
        """The signal reactive reads of a patchable instance subscribe to (created on first read)."""
        sig = self._sig
        if sig is None:
            sig = self._sig = Signal(self._raw, equals=self._wyb_same, name=type(self).__name__)
        return sig

    def _wyb_same(self, old: dict[str, Any], new: dict[str, Any]) -> bool:
        """Whether two raw prop dicts agree on every reactive field."""
        for name in type(self)._wyb_reactive:
            a = old.get(name, _MISSING)
            b = new.get(name, _MISSING)
            if a is b:
                continue
            try:
                if a == b:
                    continue
            except Exception:
                pass
            return False
        return True

    def _wyb_default(self, field: _Field) -> Any:
        """A missing field's default; a `default_factory` result is created once per instance."""
        if field.factory is None:
            return None if field.default is _MISSING else field.default
        defaults = self._defaults
        if defaults is None:
            defaults = self._defaults = {}
        if field.name not in defaults:
            defaults[field.name] = field.factory()
        return defaults[field.name]

    def _wyb_accessor(self, field: _Field) -> Accessor[Any]:
        accessors = self._accessors
        if accessors is None:
            accessors = self._accessors = {}
        accessor = accessors.get(field.name)
        if accessor is None:
            accessor = accessors[field.name] = _PropAccessor(self, field)
        return accessor

    def _wyb_update(self, values: dict[str, Any]) -> None:
        """Push new parent props into the live instance (reconciler patch path)."""
        self._raw = values
        sig = self._sig
        if sig is not None:
            sig._set(values)

    def _wyb_raw(self, name: str, default: Any = None) -> Any:
        """The parent's current value for `name`, declared or not, without tracking."""
        return self._raw.get(name, default)

    def _wyb_items(self) -> Iterator[tuple[str, Any]]:
        """Yield `(name, accessor or value)` for every declared field and passed key."""
        fields = type(self)._wyb_fields
        for name, field in fields.items():
            yield name, (self._wyb_accessor(field) if field.reactive else getattr(self, name))
        for name, value in self._raw.items():
            if name not in fields and name != "key":
                yield name, value

    def __getitem__(self, children: Any) -> Self:
        """Children sugar for type checkers: `Card(title="Hi")[h2("Body"), p("More")]`.

        At run time a component call returns a node, whose item syntax sets
        its `children` prop.
        """
        raise TypeError("Props instances don't take children; call the component instead")

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._raw!r})"


class ParentProps(Props):
    """Props for a component that renders `children`."""

    children: Prop[Any] = prop(default=None)


def _resolve_source(source: Any) -> Any:
    if isinstance(source, Accessor):
        return source()
    if callable(source) and not isinstance(source, (Mapping, Props)):
        return source()
    return source


def _lookup(source: Any, key: str, defaults: bool = True) -> tuple[bool, Any]:
    """Return `(found, value)` for `key` in a prop source (tracked read)."""
    source = _resolve_source(source)
    if source is None:
        return False, None
    if isinstance(source, Props):
        if key == "key":
            return False, None
        field = type(source)._wyb_fields.get(key)
        if key not in source._raw and (not defaults or field is None):
            return False, None
        if field is not None:
            if field.reactive:
                return True, source._wyb_accessor(field)()
            return True, getattr(source, key)
        return True, _unwrap(source._raw[key])
    if isinstance(source, Mapping):
        if key in source:
            return True, _unwrap(source[key])
        return False, None
    return False, None


def _keys(source: Any) -> list[str]:
    source = _resolve_source(source)
    if source is None:
        return []
    if isinstance(source, Props):
        return [name for name, _ in source._wyb_items()]
    if isinstance(source, Mapping):
        return list(source)
    return []


def _passes_through(key: str) -> bool:
    """Whether an element prop takes its value as is: an event handler or a ref."""
    return key == "ref" or key.startswith("on_") or (len(key) > 2 and key.startswith("on") and key[2].isupper())


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


class _PropsView(Mapping[str, Any]):
    """Base for the read-only reactive mappings returned by `merge` and `omit`."""

    __slots__ = ("_accessors",)

    def __init__(self) -> None:
        self._accessors: dict[str, _KeyAccessor] = {}

    def _resolve(self, key: str) -> Any:
        raise NotImplementedError

    def _all_keys(self) -> list[str]:
        raise NotImplementedError

    def __getitem__(self, key: str) -> Any:
        if _passes_through(key):
            # Event handlers and refs are values, never reactive bindings:
            # spreading the view must hand the element the callable itself.
            return untrack(lambda: self._resolve(key))
        acc = self._accessors.get(key)
        if acc is None:
            acc = _KeyAccessor(self, key)
            self._accessors[key] = acc
        return acc

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self._all_keys())

    def __len__(self) -> int:
        return len(self._all_keys())

    def __contains__(self, key: object) -> bool:
        return key in self._all_keys()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({untrack(lambda: {k: self._resolve(k) for k in self._all_keys()})!r})"


class _Merged(_PropsView):
    __slots__ = ("_sources",)

    def __init__(self, sources: tuple[Any, ...]) -> None:
        super().__init__()
        self._sources = sources

    def _resolve(self, key: str) -> Any:
        # Keys the parent passed win first, so defaults merged in earlier
        # sources apply (Solid's `merge(defaults, props)` pattern); declared
        # defaults are the fallback.
        for defaults in (False, True):
            for source in reversed(self._sources):
                found, value = _lookup(source, key, defaults)
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

    def __init__(self, source: Any, omit: Callable[[str], bool]) -> None:
        super().__init__()
        self._source = source
        self._omit = omit

    def _resolve(self, key: str) -> Any:
        if self._omit(key):
            return None
        _, value = _lookup(self._source, key)
        return value

    def _all_keys(self) -> list[str]:
        return [k for k in _keys(self._source) if not self._omit(k)]


def merge(*sources: Any) -> Mapping[str, Accessor[Any]]:
    """Merge prop sources into one reactive mapping; later sources win.

    Each source may be a component's props, a plain dict (values may be
    accessors or static), a zero-arg function returning a dict, or
    another merged or omitted view. Reads resolve right to left at
    access time, so tracking flows through to whichever source supplied
    the key. A key present with the value `None` overrides earlier
    sources, as an explicit `undefined` does in Solid 2.0.

    The result is a mapping of accessors: spread it onto an element
    (`button(**merge(defaults, extra))`).

    Example:
        ```python
        attrs = merge({"type": "button"}, {"disabled": props.busy})
        button("Save", **attrs)
        ```
    """
    return _Merged(sources)


def omit(source: Any, *keys: str | Callable[[str], bool]) -> Mapping[str, Accessor[Any]]:
    """Return a reactive view of `source` without some keys.

    Pass key names, or a single predicate that returns `True` for each
    key to drop. The replacement for Solid 1.x's `splitProps`: handle
    some props locally and forward the rest.

    ```python
    rest = omit(props, "label", "children")
    rest = omit(props, lambda key: key.startswith("on_"))
    ```
    """
    if len(keys) == 1 and callable(keys[0]):
        predicate = keys[0]
    else:
        names = frozenset(k for k in keys if isinstance(k, str))
        predicate = names.__contains__
    return _Omitted(source, predicate)
