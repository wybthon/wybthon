"""Component props: the props object a component reads, `prop()`, `merge`, `omit`, and `is_static`.

A component declares its inputs as parameters:

```python
@component
def Greeting(name: str, excited: bool = False, on_wave: Callable[[], None] | None = None):
    return html(t"<p>Hello, {name}{'!' if excited else '.'}</p>")
```

The compiler turns every read of a parameter in the body into a read of
the component's props object (see [`wybthon.compiler`][wybthon.compiler]),
an instance of a [`Props`][wybthon.reactivity._props.Props] subclass
built from the function's signature the first time the component is
used:

- Reading a prop returns the parent's current value, tracked, as reading
  a property of Solid's props object does. In a template `{name}` is
  therefore dynamic, so the text updates when the parent's value
  changes.
- The parent may pass a value, a getter (what the compiler makes of
  `<{Greeting} name={user().name}>`), or an accessor (a signal or memo).
  Getters are always read; accessors are read unless the parameter's
  annotation is callable. Any other function is a value like any other,
  returned exactly as the parent passed it, so a callback is never called
  by reading it, whatever its parameter is annotated.
- A `**rest` parameter is a reactive view of the props the component
  doesn't declare (`omit`'s view), which spreads onto an element.
"""

from __future__ import annotations

import annotationlib
import collections.abc
import inspect
import re
import types
import typing
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any, ClassVar

from ._core import _MISSING, Accessor, _Getter, _PropField, untrack

__all__ = ["Children", "prop", "merge", "omit", "is_static"]

type Children = Any
"""What a component's `children` parameter holds: nodes, text, a list of either, or a function returning them.

Annotate the parameter `children: Children = None`. Content arrives as a
component tag's markup, the `children` keyword, or item syntax
(`Card(title="Hi")[html(t"<p>Body</p>")]`).
"""


class _Default:
    """The marker `prop()` returns, read from a parameter's default when the props class is built."""

    __slots__ = ("factory",)

    def __init__(self, factory: Callable[[], Any]) -> None:
        self.factory = factory


def prop[T](*, default_factory: Callable[[], T]) -> T:
    """A parameter default that's created once per component instance, like `dataclasses.field`'s.

    An ordinary default (`step: int = 1`) needs no `prop()`. Use it for a
    mutable default, which would otherwise be one object shared by every
    instance:

    ```python
    @component
    def TagList(tags: list[str] = prop(default_factory=list)):
        ...
    ```
    """
    return typing.cast(T, _Default(default_factory))


# Annotations a callback parameter can have, for annotations that can't be
# evaluated yet (a name defined later in the module).
_CALLABLE_TEXT = re.compile(r"\b(?:Callable|Accessor|Signal|Memo|EventHandler)\b")
_CLASSVAR_TEXT = re.compile(r"^(?:[\w.]+\.)?ClassVar(?:\[|$)")


def _is_callable_type(annotation: Any) -> bool:
    """Whether an annotation describes a callable (a callback or an accessor).

    A union is callable when any member other than `None` is. Props of
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


class Props:
    """The props object a mounted component reads (internal).

    A component's props class is built from its signature
    ([`_wyb_from_signature`][wybthon.reactivity._props.Props._wyb_from_signature]);
    Wybthon's own built-in components subclass it with annotated fields
    and take the instance as their one parameter.

    The reconciler builds one instance per mounted component. Reading a
    field returns the parent's current value and tracks it, so a parent
    that passes an expression (or later patches in a new value) updates
    the child without re-running it.
    """

    __slots__ = ("_raw", "_sig", "_patchable", "_defaults")

    _wyb_fields: ClassVar[dict[str, _PropField]] = {}
    _wyb_required: ClassVar[frozenset[str]] = frozenset()
    _wyb_names: ClassVar[frozenset[str]] = frozenset()
    _wyb_compared: ClassVar[tuple[str, ...]] = ()
    # The names a caller may pass positionally, in order.
    _wyb_positional: ClassVar[tuple[str, ...]] = ()
    # Accepts props it doesn't declare: a component with `**rest`, and
    # built-ins that forward attributes.
    _wyb_open: ClassVar[bool] = False
    # Built-in components read their fields as the caller passed them.
    _wyb_internal: ClassVar[bool] = False
    _wyb_extras: ClassVar[dict[str, _PropField] | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        fields = dict(getattr(cls, "_wyb_fields", {}))
        annotations = annotationlib.get_annotations(cls, format=annotationlib.Format.FORWARDREF)
        for name, annotation in annotations.items():
            if name.startswith("_") or _is_classvar(annotation):
                continue
            value = cls.__dict__.get(name, _MISSING)
            if isinstance(value, _PropField):
                continue
            fields[name] = _PropField(name, not _is_callable_type(annotation), value, None, cls._wyb_internal)
        cls._wyb_install(fields)

    @classmethod
    def _wyb_install(cls, fields: dict[str, _PropField]) -> None:
        for name, field in fields.items():
            setattr(cls, name, field)
        cls._wyb_fields = fields
        cls._wyb_required = frozenset(name for name, field in fields.items() if field.required)
        cls._wyb_names = frozenset(fields)
        cls._wyb_compared = tuple(name for name, field in fields.items() if field.unwrap)

    @classmethod
    def _wyb_from_signature(cls, name: str, params: Sequence[inspect.Parameter]) -> type[Props]:
        """Build the props class of a component whose parameters are its props."""
        fields: dict[str, _PropField] = {}
        positional: list[str] = []
        is_open = False
        for param in params:
            if param.kind is param.VAR_KEYWORD:
                is_open = True
                continue
            if param.kind is param.VAR_POSITIONAL:
                raise TypeError(
                    f"Component {name} can't take *{param.name}; declare a `children` parameter for its content"
                )
            if param.kind is param.POSITIONAL_ONLY:
                raise TypeError(
                    f"Component {name} can't take positional-only parameters; props are passed by name, "
                    "as a tag's attributes are, so remove the `/`"
                )
            if param.kind is param.POSITIONAL_OR_KEYWORD:
                positional.append(param.name)
            default: Any = param.default
            factory: Callable[[], Any] | None = None
            if default is param.empty:
                default = _MISSING
            elif isinstance(default, _Default):
                default, factory = _MISSING, default.factory
            annotation = param.annotation
            unwrap = annotation is param.empty or not _is_callable_type(annotation)
            fields[param.name] = _PropField(param.name, unwrap, default, factory)
        namespace: dict[str, Any] = {"__slots__": (), "__qualname__": f"{name}.props", "__module__": cls.__module__}
        props_class = typing.cast(
            type[Props], types.new_class(f"{name}Props", (cls,), exec_body=lambda ns: ns.update(namespace))
        )
        props_class._wyb_install(fields)
        props_class._wyb_positional = tuple(positional)
        props_class._wyb_open = is_open
        return props_class

    def __init__(self, **values: Any) -> None:
        self._raw: dict[str, Any] = values
        self._sig: Any = None
        self._patchable = True
        self._defaults: dict[str, Any] | None = None

    @classmethod
    def _wyb_bind(cls, values: dict[str, Any], patchable: bool) -> Props:
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
        if "key" in values and "key" not in cls._wyb_names and not cls._wyb_internal:
            raise TypeError(
                f"{component}() got unexpected prop(s): key (components take no key; "
                "remount with Show(value, ..., keyed=True))"
            )
        if not cls._wyb_open:
            unknown = values.keys() - cls._wyb_names
            if unknown:
                raise TypeError(f"{component}() got unexpected prop(s): {', '.join(sorted(unknown))}")
        # Item syntax (`Card(title="Hi")[...]`) sets `children` after the call,
        # so a missing `children` isn't an error here (it reads as `None`);
        # type checkers and `wyb check` still report it.
        missing = cls._wyb_required - values.keys() - {"children"}
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
        names = type(self)._wyb_compared
        if type(self)._wyb_open:
            names = (*names, *((old.keys() | new.keys()) - type(self)._wyb_names))
        for name in names:
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
            sig._write(values)

    def _wyb_raw(self, name: str, default: Any = None) -> Any:
        """The parent's current value for `name` as passed, declared or not, without tracking."""
        return self._raw.get(name, default)

    @classmethod
    def _wyb_extra(cls, key: str) -> _PropField:
        """The field that reads an undeclared key (cached per class)."""
        extras = cls.__dict__.get("_wyb_extras")
        if extras is None:
            extras = {}
            cls._wyb_extras = extras
        field = extras.get(key)
        if field is None:
            field = extras[key] = _PropField(key, not _passes_through(key), _MISSING, None)
        return field

    def _wyb_rest(self) -> Any:
        """The reactive view of the props this component doesn't declare (its `**rest` parameter)."""
        names = type(self)._wyb_names
        return _Omitted(self, lambda key: key in names or key == "key")

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._raw!r})"


def _passes_through(key: str) -> bool:
    """Whether a key's value is used as is: an event handler or a ref."""
    return key == "ref" or key.startswith("on_")


def _value(key: str, value: Any) -> Any:
    """Read one raw value: getters and accessors are called, except for handlers and refs."""
    if type(value) is _Getter:
        return value.fn()
    if not _passes_through(key) and isinstance(value, Accessor):
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
        if field is None:
            # An undeclared key (a `**rest` prop) reads like a declared one:
            # tracked, so a re-rendering parent's new value reaches it.
            field = source._wyb_extra(key)
        return True, field.__get__(source)
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

    Each source may be a component's `**rest` parameter, a plain dict
    (values may be accessors or static), a zero-argument function returning a dict, or
    another merged or omitted view. Reads resolve right to left at access
    time, so tracking flows through to whichever source supplied the key.
    A key present with the value `None` overrides earlier sources, as an
    explicit `undefined` does in Solid 2.0.

    Read a key as an attribute (`view.title`), or spread the view onto an
    element to bind every key.

    Example:
        ```python
        @component
        def SaveButton(**rest: Any):
            attrs = merge({"type": "button"}, rest)
            return html(t"<button {attrs}>Save</button>")
        ```
    """
    return _Merged(sources)


def omit(source: Any, *keys: str | Callable[[str], bool]) -> Any:
    """Return a reactive view of `source` without some keys.

    Pass key names, or a single predicate that returns `True` for each
    key to drop. A component's `**rest` parameter is already the view of
    the props it doesn't declare; `omit` narrows a view further:

    ```python
    @component
    def Field(label: str, **rest: Any):
        attrs = omit(rest, lambda key: key.startswith("on_"))
        return html(t"<label>{label}<input {attrs}></label>")
    ```
    """
    if len(keys) == 1 and callable(keys[0]):
        predicate = keys[0]
    else:
        names = frozenset(k for k in keys if isinstance(k, str))
        predicate = names.__contains__
    return _Omitted(source, predicate)


def is_static(source: Any, key: str | None = None) -> bool:
    """Whether the parent passed a prop as a plain value rather than an expression.

    The counterpart of Solid 2.0's `isStatic`. A component library can
    take a cheaper path for a prop that can't change: in a compiled
    template, `<{Button} kind="primary">` passes a value, while
    `<{Button} kind={variant()}>` passes a getter. Accessors count as
    expressions; a prop the parent didn't pass is static. Nothing is
    read or tracked.

    Inside a component, pass the parameter itself: the compiler turns
    `is_static(name)` into a question about the prop, not its value.
    `is_static(view, "key")` asks the same of a key of a `merge` or
    `omit` view (or a `**rest` parameter).

    ```python
    @component
    def Icon(name: str):
        if is_static(name):
            return html(t"<i class={untrack(lambda: name)}></i>")
        return html(t"<i class={name}></i>")
    ```
    """
    if key is None:
        raise TypeError(
            "is_static(param) asks about a parameter of a compiled component; "
            "elsewhere, pass a props view and a key: is_static(view, 'key')"
        )
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
    return not isinstance(value, Accessor)
