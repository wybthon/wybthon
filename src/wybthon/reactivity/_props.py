"""Component props: typed `Props` classes, `prop()` defaults, `merge`, `omit`, and `is_static`.

A component declares its inputs on a subclass of [`Props`][wybthon.Props]
and takes one parameter annotated with that class:

```python
class GreetingProps(Props):
    name: str
    excited: bool = False
    on_wave: Callable[[], None] | None = None


@component
def Greeting(props: GreetingProps):
    return html(t"<p>Hello, {props.name}{'!' if props.excited else '.'}</p>")
```

- Reading `props.name` returns the parent's current value, tracked, as
  reading a property of Solid's props object does. In a template the
  compiler turns `{props.name}` into a getter, so the text updates when
  the parent's value changes.
- The parent may pass a value, a getter (what the compiler makes of
  `<{Greeting} name={user().name}>`), or an accessor. Getters are always
  unwrapped; accessors are unwrapped unless the field's annotation is
  callable, so a callback is returned exactly as the parent passed it.
- `Props` is a PEP 681 `dataclass_transform` base, so pyright and mypy
  check component calls without a plugin.
"""

from __future__ import annotations

import annotationlib
import collections.abc
import re
import types
import typing
from collections.abc import Callable, Iterator, Mapping
from typing import Any, ClassVar, Self, dataclass_transform, overload

from ._core import _MISSING, Accessor, _Getter, _PropField, is_accessor, untrack

__all__ = ["Props", "ParentProps", "prop", "merge", "omit", "is_static"]


class _Default:
    """The marker `prop()` returns; replaced by the field's descriptor at class creation."""

    __slots__ = ("default", "factory")

    def __init__(self, default: Any, factory: Callable[[], Any] | None) -> None:
        self.default = default
        self.factory = factory


@overload
def prop[T](*, default: T) -> T: ...
@overload
def prop[T](*, default_factory: Callable[[], T]) -> T: ...
def prop(*, default: Any = _MISSING, default_factory: Callable[[], Any] | None = None) -> Any:
    """Declare a field's default, like `dataclasses.field`.

    An ordinary default (`step: int = 1`) needs no `prop()`. Use
    `default_factory` for mutable defaults: the factory runs once per
    component instance. Type checkers only recognize a field specifier's
    default when it's passed by keyword.

    ```python
    class ListProps(Props):
        tags: list[str] = prop(default_factory=list)
    ```
    """
    if (default is _MISSING) == (default_factory is None):
        raise TypeError("prop() takes exactly one of default= or default_factory=")
    return _Default(default, default_factory)


# Annotations a callback field can have, for annotations that can't be
# evaluated when the class is created (a name defined later in the module).
_CALLABLE_TEXT = re.compile(r"\b(?:Callable|Accessor|Signal|Memo|EventHandler)\b")
_CLASSVAR_TEXT = re.compile(r"^(?:[\w.]+\.)?ClassVar(?:\[|$)")


def _is_callable_type(annotation: Any) -> bool:
    """Whether a field annotation describes a callable (a callback or an accessor).

    A union is callable when any member other than `None` is. Fields of
    these types return the parent's value as passed instead of calling it.
    """
    if isinstance(annotation, str):
        return bool(_CALLABLE_TEXT.search(annotation))
    if isinstance(annotation, annotationlib.ForwardRef):
        return bool(_CALLABLE_TEXT.search(annotation.__forward_arg__))
    if isinstance(annotation, typing.TypeAliasType):
        return _is_callable_type(annotation.__value__)
    origin = typing.get_origin(annotation)
    if origin is typing.Annotated:
        return _is_callable_type(typing.get_args(annotation)[0])
    if origin is typing.Union or origin is types.UnionType:
        return any(_is_callable_type(arg) for arg in typing.get_args(annotation) if arg is not type(None))
    if annotation is collections.abc.Callable or origin is collections.abc.Callable:
        return True
    target = origin if origin is not None else annotation
    if isinstance(target, type):
        if issubclass(target, Accessor):
            return True
        if typing.is_protocol(target) and "__call__" in typing.get_protocol_members(target):
            return True
        if target.__name__ == "EventHandler":
            return True
    return False


def _is_classvar(annotation: Any) -> bool:
    if isinstance(annotation, str):
        return bool(_CLASSVAR_TEXT.match(annotation))
    if isinstance(annotation, annotationlib.ForwardRef):
        return bool(_CLASSVAR_TEXT.match(annotation.__forward_arg__))
    return annotation is ClassVar or typing.get_origin(annotation) is ClassVar


@dataclass_transform(kw_only_default=True, frozen_default=True, field_specifiers=(prop,))
class _PropsBase:
    """Gives `Props` subclasses their checked keyword constructor (PEP 681)."""

    __slots__ = ()


class Props(_PropsBase):
    """Base class for a component's declared inputs.

    Subclass it, annotate fields, and take one parameter of that type in
    the component. Every component also accepts `key`, which gives the
    instance a stable identity for keyed reconciliation.

    At run time the reconciler builds one instance per mounted component.
    Reading a field returns the parent's current value and tracks it, so a
    parent that passes an expression (or later patches in a new value)
    updates the child without re-running it.
    """

    __slots__ = ("_raw", "_sig", "_patchable", "_defaults")

    key: str | int | None = None

    _wyb_fields: ClassVar[dict[str, _PropField]] = {}
    _wyb_required: ClassVar[frozenset[str]] = frozenset()
    _wyb_names: ClassVar[frozenset[str]] = frozenset({"key"})
    _wyb_compared: ClassVar[tuple[str, ...]] = ()
    # Internal props classes (built-in components that forward attributes)
    # accept keys they don't declare.
    _wyb_open: ClassVar[bool] = False
    # Built-in components read their fields as the caller passed them.
    _wyb_internal: ClassVar[bool] = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        fields = dict(getattr(cls, "_wyb_fields", {}))
        annotations = annotationlib.get_annotations(cls, format=annotationlib.Format.FORWARDREF)
        for name, annotation in annotations.items():
            if name.startswith("_") or name == "key" or _is_classvar(annotation):
                continue
            value = cls.__dict__.get(name, _MISSING)
            if isinstance(value, _Default):
                default, factory = value.default, value.factory
            elif isinstance(value, _PropField):
                continue
            else:
                default, factory = value, None
            field = _PropField(name, not _is_callable_type(annotation), default, factory, cls._wyb_internal)
            fields[name] = field
            setattr(cls, name, field)
        cls._wyb_fields = fields
        cls._wyb_required = frozenset(name for name, field in fields.items() if field.required)
        cls._wyb_names = frozenset(fields) | {"key"}
        cls._wyb_compared = tuple(name for name, field in fields.items() if field.unwrap)

    def __init__(self, **values: Any) -> None:
        self._raw: dict[str, Any] = values
        self._sig: Any = None
        self._patchable = True
        self._defaults: dict[str, Any] | None = None

    @classmethod
    def _wyb_bind(cls, values: dict[str, Any], patchable: bool) -> Self:
        """The live instance a mounted component reads (reconciler internal)."""
        instance = cls.__new__(cls)
        instance._raw = values
        instance._sig = None
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

    def _wyb_signal(self) -> Any:
        """The signal reads of a patchable instance subscribe to (created on first read)."""
        sig = self._sig
        if sig is None:
            from ._core import Signal

            sig = self._sig = Signal(self._raw, equals=self._wyb_same, name=type(self).__name__)
        return sig

    def _wyb_same(self, old: dict[str, Any], new: dict[str, Any]) -> bool:
        """Whether two raw prop dicts agree on every field whose reads are values (not callbacks)."""
        for name in type(self)._wyb_compared:
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

    def _wyb_default(self, field: _PropField) -> Any:
        """A missing field's default; a `default_factory` result is created once per instance."""
        if field.factory is None:
            return None if field.default is _MISSING else field.default
        defaults = self._defaults
        if defaults is None:
            defaults = self._defaults = {}
        if field.name not in defaults:
            defaults[field.name] = field.factory()
        return defaults[field.name]

    def _wyb_update(self, values: dict[str, Any]) -> None:
        """Push new parent props into the live instance (reconciler patch path)."""
        self._raw = values
        sig = self._sig
        if sig is not None:
            sig._set(values)

    def _wyb_raw(self, name: str, default: Any = None) -> Any:
        """The parent's current value for `name` as passed, declared or not, without tracking."""
        return self._raw.get(name, default)

    def __getitem__(self, children: Any) -> Self:
        """Children sugar for type checkers: `Card(title="Hi")[h("p", None, "Body")]`.

        At run time a component call returns a node, whose item syntax sets
        its `children` prop.
        """
        raise TypeError("Props instances don't take children; call the component instead")

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._raw!r})"


class ParentProps(Props):
    """Props for a component that renders `children`."""

    children: Any = None


def _passes_through(key: str) -> bool:
    """Whether a key's value is used as is: an event handler or a ref."""
    return key == "ref" or key.startswith("on_") or (len(key) > 2 and key.startswith("on") and key[2].isupper())


def _value(key: str, value: Any) -> Any:
    """Read one raw value: getters and accessors are called, except for handlers and refs."""
    if type(value) is _Getter:
        return value.fn()
    if not _passes_through(key) and is_accessor(value):
        return value()
    return value


def _resolve_source(source: Any) -> Any:
    if type(source) is _Getter or (isinstance(source, Accessor) and not isinstance(source, _PropsView)):
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
            return True, field.__get__(source)
        return True, _value(key, source._raw[key])
    if isinstance(source, _PropsView):
        if key in source._all_keys():
            return True, source._resolve(key)
        return False, None
    if isinstance(source, Mapping):
        if key in source:
            return True, _value(key, source[key])
        return False, None
    return False, None


def _raw_lookup(source: Any, key: str) -> tuple[bool, Any]:
    """Return `(found, raw value)` for `key`, as the parent passed it (untracked)."""
    if type(source) is _Getter or (callable(source) and not isinstance(source, (Mapping, Props, _PropsView))):
        source = untrack(source)
    if source is None:
        return False, None
    if isinstance(source, Props):
        if key in source._raw:
            return True, source._raw[key]
        return False, None
    if isinstance(source, _PropsView):
        return source._raw(key)
    if isinstance(source, Mapping):
        if key in source:
            return True, source[key]
    return False, None


def _keys(source: Any) -> list[str]:
    source = _resolve_source(source)
    if source is None:
        return []
    if isinstance(source, Props):
        fields = type(source)._wyb_fields
        return list(fields) + [name for name in source._raw if name not in fields and name != "key"]
    if isinstance(source, _PropsView):
        return source._all_keys()
    if isinstance(source, Mapping):
        return list(source)
    return []


class _KeyAccessor(Accessor[Any]):
    """Accessor for one key of a merged or omitted props view (what spreading binds)."""

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
    """Base for the read-only reactive views returned by `merge` and `omit`.

    Attribute access reads a value, tracked, like a component's props:
    `view.title`. Item access returns an accessor per key, so spreading a
    view onto an element (`<div {view}>`) binds each attribute reactively;
    event handlers and refs come back as the callables themselves.
    """

    __slots__ = ("_accessors",)

    def __init__(self) -> None:
        self._accessors: dict[str, _KeyAccessor] = {}

    def _resolve(self, key: str) -> Any:
        raise NotImplementedError

    def _raw(self, key: str) -> tuple[bool, Any]:
        raise NotImplementedError

    def _all_keys(self) -> list[str]:
        raise NotImplementedError

    def __getitem__(self, key: str) -> Any:
        if _passes_through(key):
            return untrack(lambda: self._resolve(key))
        acc = self._accessors.get(key)
        if acc is None:
            acc = _KeyAccessor(self, key)
            self._accessors[key] = acc
        return acc

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return self._resolve(name)

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

    def _raw(self, key: str) -> tuple[bool, Any]:
        for source in reversed(self._sources):
            found, value = _raw_lookup(source, key)
            if found:
                return True, value
        return False, None

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

    def _raw(self, key: str) -> tuple[bool, Any]:
        if self._omit(key):
            return False, None
        return _raw_lookup(self._source, key)

    def _all_keys(self) -> list[str]:
        return [k for k in _keys(self._source) if not self._omit(k)]


def merge(*sources: Any) -> Any:
    """Merge prop sources into one reactive view; later sources win.

    Each source may be a component's props, a plain dict (values may be
    accessors or static), a zero-argument function returning a dict, or
    another merged or omitted view. Reads resolve right to left at access
    time, so tracking flows through to whichever source supplied the key.
    A key present with the value `None` overrides earlier sources, as an
    explicit `undefined` does in Solid 2.0.

    Read a key as an attribute (`view.title`), or spread the view onto an
    element to bind every key.

    Example:
        ```python
        attrs = merge({"type": "button"}, props)
        html(t"<button {attrs}>Save</button>")
        ```
    """
    return _Merged(sources)


def omit(source: Any, *keys: str | Callable[[str], bool]) -> Any:
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


def is_static(source: Any, key: str) -> bool:
    """Whether the parent passed `key` as a plain value rather than an expression.

    The counterpart of Solid 2.0's `isStatic`. A component library can
    take a cheaper path for a prop that can't change: in a compiled
    template, `<{Button} kind="primary">` passes a value, while
    `<{Button} kind={variant()}>` passes a getter. Accessors count as
    expressions; a key the parent didn't pass is static. Nothing is
    read or tracked.

    ```python
    @component
    def Icon(props: IconProps):
        if is_static(props, "name"):
            return html(t"<i class={untrack(lambda: props.name)}></i>")
        return html(t"<i class={props.name}></i>")
    ```
    """
    found, value = _raw_lookup(source, key)
    if not found:
        return True
    if type(value) is _Getter:
        return False
    if _passes_through(key):
        return True
    if isinstance(source, Props):
        field = type(source)._wyb_fields.get(key)
        if field is not None and not field.unwrap:
            return True
    return not is_accessor(value)
