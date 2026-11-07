"""The wire format for values that cross between the server and the browser.

Server functions send their arguments and results in it, and server
rendering sends resolved async values to the browser in it. It's JSON
with a few tagged objects for the Python values JSON can't represent:

| Value | Encoded as |
| --- | --- |
| `None`, `bool`, `int`, `float`, `str`, `list` | Themselves |
| `dict` with string keys | Itself, unless a key starts with `$` |
| Any other `dict` | `{"$m": [[key, value], ...]}` |
| `tuple`, `set`, `frozenset` | `{"$t": [...]}`, `{"$s": [...]}`, `{"$f": [...]}` |
| `datetime`, `date`, `time` | `{"$dt": iso}`, `{"$d": iso}`, `{"$tm": iso}` |
| `timedelta` | `{"$td": seconds}` |
| `Decimal`, `UUID`, `bytes` | `{"$dec": str}`, `{"$u": str}`, `{"$b": base64}` |
| A dataclass instance | `{"$dc": "module:Qualname", "v": {field: value}}` |
| An `Enum` member | `{"$e": "module:Qualname", "v": value}` |

Decoding comes in two strengths:

- **Trusted** ([`loads`][wybthon._wire.loads], the default): the browser
  decoding what its own server sent. A dataclass or enum tag is rebuilt
  as that class when its module is already imported; nothing is ever
  imported by name, and a dataclass is rebuilt without calling its
  `__init__`, as `snapshot` does.
- **Untrusted** (`loads(text, trusted=False)`): the server decoding what
  a browser sent. Class tags are ignored (a dataclass arrives as its
  field dict), and [`coerce`][wybthon._wire.coerce] then builds and
  validates each argument from the server function's own annotations.
  A client can't make the server instantiate anything the function
  didn't declare.
"""

from __future__ import annotations

import dataclasses
import datetime
import enum
import json
import sys
import types
import typing
from collections.abc import Callable, Mapping, Sequence
from typing import Any

__all__ = ["WireError", "dumps", "loads", "encode", "decode", "coerce", "parameters"]


class WireError(ValueError):
    """A value can't be encoded, or decoded data doesn't match its annotation."""


def _class_name(cls: type) -> str:
    return f"{cls.__module__}:{cls.__qualname__}"


def encode(value: Any) -> Any:
    """Convert `value` to plain JSON data, tagging what JSON can't represent."""
    t = type(value)
    if value is None or t is bool or t is int or t is str:
        return value
    if t is float:
        return value
    if t is list:
        return [encode(item) for item in value]
    if t is dict:
        if all(type(key) is str and not key.startswith("$") for key in value):
            return {key: encode(item) for key, item in value.items()}
        return {"$m": [[encode(key), encode(item)] for key, item in value.items()]}
    if t is tuple:
        return {"$t": [encode(item) for item in value]}
    if isinstance(value, enum.Enum):
        return {"$e": _class_name(t), "v": encode(value.value)}
    # Subclasses of the plain types (an `IntEnum` was handled above).
    for plain in (bool, int, float, str):
        if isinstance(value, plain):
            return plain(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        fields = {field.name: encode(getattr(value, field.name)) for field in dataclasses.fields(value)}
        return {"$dc": _class_name(t), "v": fields}
    if isinstance(value, datetime.datetime):
        return {"$dt": value.isoformat()}
    if isinstance(value, datetime.date):
        return {"$d": value.isoformat()}
    if isinstance(value, datetime.time):
        return {"$tm": value.isoformat()}
    if isinstance(value, datetime.timedelta):
        return {"$td": value.total_seconds()}
    # `decimal` and `uuid` load only when the application uses them: a value
    # can't be a Decimal or a UUID before its module is imported.
    decimal = sys.modules.get("decimal")
    if decimal is not None and isinstance(value, decimal.Decimal):
        return {"$dec": str(value)}
    uuid = sys.modules.get("uuid")
    if uuid is not None and isinstance(value, uuid.UUID):
        return {"$u": str(value)}
    if isinstance(value, bytes | bytearray | memoryview):
        import base64

        return {"$b": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, frozenset):
        return {"$f": [encode(item) for item in value]}
    if isinstance(value, set):
        return {"$s": [encode(item) for item in value]}
    if isinstance(value, Mapping):
        return encode(dict(value))
    if isinstance(value, Sequence):
        return [encode(item) for item in value]
    snapshot = getattr(value, "_wyb_snapshot", None)
    if callable(snapshot):
        # A store view crosses as the plain data it holds.
        return encode(snapshot())
    raise WireError(f"{t.__qualname__} values can't be sent between the server and the browser")


def dumps(value: Any) -> str:
    """Encode `value` as wire-format JSON text."""
    return json.dumps(encode(value), separators=(",", ":"), ensure_ascii=False)


def _resolve(name: str) -> type | None:
    """An already imported class by `module:Qualname`; never imports anything."""
    module_name, _, qualname = name.partition(":")
    module = sys.modules.get(module_name)
    if module is None:
        return None
    target: Any = module
    for part in qualname.split("."):
        target = getattr(target, part, None)
        if target is None:
            return None
    return target if isinstance(target, type) else None


def _rebuild(cls: type, fields: dict[str, Any]) -> Any:
    instance: Any = object.__new__(cls)
    for field in dataclasses.fields(cls):
        if field.name in fields:
            object.__setattr__(instance, field.name, fields[field.name])
        elif field.default is not dataclasses.MISSING:
            object.__setattr__(instance, field.name, field.default)
        elif field.default_factory is not dataclasses.MISSING:
            object.__setattr__(instance, field.name, field.default_factory())
    return instance


def decode(data: Any, *, trusted: bool = True) -> Any:
    """Turn plain JSON data back into Python values (see the module docs for `trusted`)."""
    t = type(data)
    if t is list:
        return [decode(item, trusted=trusted) for item in data]
    if t is not dict:
        return data
    if len(data) == 1 or (len(data) == 2 and "v" in data):
        for tag, raw in data.items():
            if tag == "v" or not tag.startswith("$"):
                continue
            if tag == "$t":
                return tuple(decode(item, trusted=trusted) for item in raw)
            if tag == "$s":
                return {decode(item, trusted=trusted) for item in raw}
            if tag == "$f":
                return frozenset(decode(item, trusted=trusted) for item in raw)
            if tag == "$m":
                return {decode(key, trusted=trusted): decode(item, trusted=trusted) for key, item in raw}
            if tag == "$dt":
                return datetime.datetime.fromisoformat(raw)
            if tag == "$d":
                return datetime.date.fromisoformat(raw)
            if tag == "$tm":
                return datetime.time.fromisoformat(raw)
            if tag == "$td":
                return datetime.timedelta(seconds=raw)
            if tag == "$dec":
                import decimal

                return decimal.Decimal(raw)
            if tag == "$u":
                import uuid

                return uuid.UUID(raw)
            if tag == "$b":
                import base64

                return base64.b64decode(raw)
            if tag == "$dc":
                fields = {key: decode(item, trusted=trusted) for key, item in (data.get("v") or {}).items()}
                cls = _resolve(raw) if trusted else None
                if cls is not None and dataclasses.is_dataclass(cls):
                    return _rebuild(cls, fields)
                return fields
            if tag == "$e":
                value = decode(data.get("v"), trusted=trusted)
                cls = _resolve(raw) if trusted else None
                if cls is not None and issubclass(cls, enum.Enum):
                    try:
                        return cls(value)
                    except ValueError:
                        pass
                return value
    return {key: decode(item, trusted=trusted) for key, item in data.items()}


def loads(text: str | bytes, *, trusted: bool = True) -> Any:
    """Decode wire-format JSON text."""
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise WireError(f"Malformed wire data: {exc}") from exc
    return decode(data, trusted=trusted)


# ---------------------------------------------------------------------------
# Building values from annotations (untrusted input)
# ---------------------------------------------------------------------------


def _fail(path: str, expected: str, value: Any) -> WireError:
    return WireError(f"{path or 'value'}: expected {expected}, got {type(value).__qualname__}")


def coerce(value: Any, annotation: Any, path: str = "") -> Any:
    """Build a value of type `annotation` from decoded data, or raise `WireError`.

    Supported: `Any`, `object`, the plain types, `list`, `tuple`, `dict`,
    `set`, `frozenset`, abstract collections, unions and `Optional`,
    `Literal`, dataclasses, `TypedDict`s, enums, and the tagged types
    (`datetime`, `Decimal`, and so on, which also accept their string
    form). An annotation it doesn't know passes the value through.
    """
    if annotation is Any or annotation is object or annotation is typing.Any:
        return value
    if annotation is None or annotation is type(None):
        if value is not None:
            raise _fail(path, "None", value)
        return None
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin is typing.Annotated:
        return coerce(value, args[0], path)
    if origin is typing.Union or origin is types.UnionType:
        if value is None and type(None) in args:
            return None
        errors: list[str] = []
        for option in args:
            if option is type(None):
                continue
            try:
                return coerce(value, option, path)
            except WireError as exc:
                errors.append(str(exc))
        raise WireError(errors[0] if len(errors) == 1 else f"{path or 'value'}: matched none of {annotation}")
    if origin is typing.Literal:
        if value in args:
            return value
        raise WireError(f"{path or 'value'}: expected one of {list(args)!r}, got {value!r}")
    if isinstance(annotation, typing.TypeAliasType):
        return coerce(value, annotation.__value__, path)
    target = origin if origin is not None else annotation
    if target is bool:
        if type(value) is not bool:
            raise _fail(path, "bool", value)
        return value
    if target is int:
        if type(value) is not int:
            raise _fail(path, "int", value)
        return value
    if target is float:
        if type(value) not in (int, float):
            raise _fail(path, "float", value)
        return float(value)
    if target is str:
        if type(value) is not str:
            raise _fail(path, "str", value)
        return value
    if target is bytes:
        if type(value) is not bytes:
            raise _fail(path, "bytes", value)
        return value
    parse = _scalar(target)
    if parse is not None:
        if isinstance(value, target) and not (target is datetime.date and isinstance(value, datetime.datetime)):
            return value
        if isinstance(value, str | int | float):
            try:
                return parse(value)
            except (ValueError, TypeError, ArithmeticError) as exc:
                raise WireError(f"{path or 'value'}: {exc}") from exc
        raise _fail(path, target.__qualname__, value)
    if isinstance(target, type) and issubclass(target, enum.Enum):
        try:
            return target(value)
        except ValueError as exc:
            raise WireError(f"{path or 'value'}: {exc}") from exc
    if isinstance(target, type) and dataclasses.is_dataclass(target):
        if isinstance(value, target):
            return value
        if type(value) is not dict:
            raise _fail(path, target.__qualname__, value)
        hints = _hints(target)
        built: dict[str, Any] = {}
        for field in dataclasses.fields(target):
            if field.name in value:
                built[field.name] = coerce(value[field.name], hints.get(field.name, Any), f"{path}.{field.name}")
            elif field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING:
                raise WireError(f"{path or target.__qualname__}: missing field {field.name!r}")
        unknown = value.keys() - {field.name for field in dataclasses.fields(target)}
        if unknown:
            raise WireError(f"{path or target.__qualname__}: unknown fields {sorted(unknown)!r}")
        try:
            return target(**built)
        except (TypeError, ValueError) as exc:
            raise WireError(f"{path or target.__qualname__}: {exc}") from exc
    if typing.is_typeddict(target):
        if type(value) is not dict:
            raise _fail(path, target.__qualname__, value)
        hints = _hints(target)
        required: frozenset[str] = getattr(target, "__required_keys__", frozenset())
        missing = required - value.keys()
        if missing:
            raise WireError(f"{path or target.__qualname__}: missing keys {sorted(missing)!r}")
        unknown = value.keys() - hints.keys()
        if unknown:
            raise WireError(f"{path or target.__qualname__}: unknown keys {sorted(unknown)!r}")
        return {key: coerce(item, hints[key], f"{path}[{key!r}]") for key, item in value.items()}
    if target in (list, Sequence, typing.Sequence) or target is _abc("Sequence") or target is _abc("MutableSequence"):
        if type(value) not in (list, tuple):
            raise _fail(path, "list", value)
        item_type = args[0] if args else Any
        return [coerce(item, item_type, f"{path}[{index}]") for index, item in enumerate(value)]
    if target is tuple:
        if type(value) not in (list, tuple):
            raise _fail(path, "tuple", value)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(coerce(item, args[0], f"{path}[{index}]") for index, item in enumerate(value))
        if args and args != ((),):
            if len(args) != len(value):
                raise WireError(f"{path or 'value'}: expected {len(args)} items, got {len(value)}")
            return tuple(coerce(item, kind, f"{path}[{index}]") for index, (item, kind) in enumerate(zip(value, args)))
        return tuple(value)
    if target in (set, frozenset) or target is _abc("Set") or target is _abc("MutableSet"):
        if type(value) not in (list, tuple, set, frozenset):
            raise _fail(path, "set", value)
        item_type = args[0] if args else Any
        items = [coerce(item, item_type, f"{path}[{index}]") for index, item in enumerate(value)]
        return frozenset(items) if target is frozenset else set(items)
    if target in (dict, Mapping) or target is _abc("Mapping") or target is _abc("MutableMapping"):
        if type(value) is not dict:
            raise _fail(path, "dict", value)
        key_type, item_type = (args[0], args[1]) if len(args) == 2 else (Any, Any)
        return {
            coerce(key, key_type, f"{path}<key>"): coerce(item, item_type, f"{path}[{key!r}]")
            for key, item in value.items()
        }
    if isinstance(target, type) and isinstance(value, target):
        return value
    if isinstance(target, type) and target.__module__ not in ("typing", "collections.abc", "builtins"):
        # A class the codec can't build from data (a FormData, say): only an
        # instance of it is acceptable.
        raise _fail(path, target.__qualname__, value)
    return value


def _abc(name: str) -> Any:
    import collections.abc

    return getattr(collections.abc, name)


_SCALARS: dict[type, Callable[[Any], Any]] = {
    datetime.datetime: lambda raw: datetime.datetime.fromisoformat(raw),
    datetime.date: lambda raw: datetime.date.fromisoformat(raw),
    datetime.time: lambda raw: datetime.time.fromisoformat(raw),
    datetime.timedelta: lambda raw: datetime.timedelta(seconds=float(raw)),
}


def _scalar(target: Any) -> Callable[[Any], Any] | None:
    """How to parse a tagged scalar type from its string form, when `target` is one."""
    parse = _SCALARS.get(target) if isinstance(target, type) else None
    if parse is not None:
        return parse
    module = getattr(target, "__module__", None)
    if module == "decimal" and getattr(target, "__name__", "") == "Decimal":
        return lambda raw: target(str(raw))
    if module == "uuid" and getattr(target, "__name__", "") == "UUID":
        return lambda raw: target(str(raw))
    return None


def _hints(target: Any) -> dict[str, Any]:
    try:
        return typing.get_type_hints(target, include_extras=True)
    except Exception:
        return dict(getattr(target, "__annotations__", {}))


def parameters(fn: Callable[..., Any]) -> tuple[list[tuple[str, Any, Any]], Any]:
    """`fn`'s parameters as `(name, annotation, kind)`, and its return annotation."""
    import inspect

    hints = _hints(fn)
    signature = inspect.signature(fn)
    params = [(name, hints.get(name, Any), param.kind) for name, param in signature.parameters.items()]
    return params, hints.get("return", Any)
