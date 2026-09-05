"""Mypy support for accessor props and TypedDict-backed stores.

Enable with ``plugins = wybthon.mypy_plugin`` in the mypy configuration.
The module is loaded only by mypy; applications don't depend on mypy.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mypy.nodes import ARG_NAMED, ARG_NAMED_OPT, ARG_OPT, ARG_STAR, ARG_STAR2, StrExpr
from mypy.plugin import AttributeContext, FunctionContext, MethodContext, MethodSigContext, Plugin
from mypy.types import (
    AnyType,
    CallableType,
    Instance,
    TupleType,
    Type,
    TypedDictType,
    TypeOfAny,
    UnionType,
    get_proper_type,
)


def _named(api: Any, fullname: str, args: list[Type]) -> Instance:
    module, _, name = fullname.rpartition(".")
    symbol = api.modules[module].names[name]
    return Instance(symbol.node, args)


def _wrapped(value: Type, api: Any, *, draft: bool = False) -> Type:
    proper = get_proper_type(value)
    if isinstance(proper, TypedDictType):
        return _named(api, "wybthon.store.Draft" if draft else "wybthon.store.Store", [value])
    if isinstance(proper, Instance) and proper.type.fullname == "builtins.list":
        return _named(
            api,
            "wybthon.store.DraftList" if draft else "wybthon.store.StoreList",
            [_wrapped(proper.args[0], api, draft=draft)],
        )
    return value


def _component_signature(ctx: MethodSigContext) -> CallableType:
    instance = get_proper_type(ctx.type)
    if not isinstance(instance, Instance) or not instance.args:
        return ctx.default_signature
    function = get_proper_type(instance.args[0])
    if not isinstance(function, CallableType):
        return ctx.default_signature
    if len(function.arg_types) == 1:
        only = get_proper_type(function.arg_types[0])
        if isinstance(only, Instance) and only.type.fullname == "wybthon.reactivity._props.Props":
            return ctx.default_signature
        if function.arg_names == ["props"] and isinstance(only, AnyType):
            return ctx.default_signature
    any_type = AnyType(TypeOfAny.explicit)
    types: list[Type] = [any_type]
    names: list[str | None] = [None]
    kinds = [ARG_STAR]
    for name, value, kind in zip(function.arg_names, function.arg_types, function.arg_kinds, strict=True):
        if kind == ARG_STAR:
            continue
        if kind == ARG_STAR2:
            types.append(any_type)
            names.append(name)
            kinds.append(ARG_STAR2)
            continue
        proper = get_proper_type(value)
        if isinstance(proper, Instance) and proper.type.fullname == "wybthon.reactivity._core.Prop":
            inner = proper.args[0]
            expression = CallableType([], [], [], inner, _named(ctx.api, "builtins.function", []))
            value = UnionType.make_union(
                [
                    inner,
                    _named(ctx.api, "wybthon.reactivity._core.Accessor", [inner]),
                    expression,
                    _named(ctx.api, "wybthon.reactivity._core.LiteralValue", [inner]),
                ]
            )
        types.append(value)
        names.append(name)
        kinds.append(ARG_NAMED_OPT if kind in (ARG_OPT, ARG_NAMED_OPT) or name == "children" else ARG_NAMED)
    if "key" not in names:
        position = len(types) - 1 if kinds[-1] == ARG_STAR2 else len(types)
        types.insert(position, any_type)
        names.insert(position, "key")
        kinds.insert(position, ARG_NAMED_OPT)
    return ctx.default_signature.copy_modified(arg_types=types, arg_names=names, arg_kinds=kinds)


def _store_created(ctx: FunctionContext) -> Type:
    result = get_proper_type(ctx.default_return_type)
    if not isinstance(result, TupleType) or not ctx.arg_types or not ctx.arg_types[0]:
        return result
    initial = ctx.arg_types[0][0]
    proper = get_proper_type(initial)
    if isinstance(proper, TypedDictType) or isinstance(proper, Instance) and proper.type.fullname == "builtins.list":
        read = _wrapped(initial, ctx.api)
        draft = _wrapped(initial, ctx.api, draft=True)
        setter = _named(ctx.api, "wybthon.store.StoreSetter", [draft])
        return result.copy_modified(items=[read, setter])
    return result


def _field(instance: Type, key: str, api: Any, fallback: Type, context: Any) -> Type:
    proper = get_proper_type(instance)
    if isinstance(proper, Instance) and proper.args:
        schema = get_proper_type(proper.args[0])
        if isinstance(schema, TypedDictType):
            if key not in schema.items:
                api.fail(f"Unknown store field: {key}", context)
                return fallback
            return _wrapped(schema.items[key], api, draft=proper.type.fullname == "wybthon.store.Draft")
    return fallback


def _item(ctx: MethodContext) -> Type:
    if ctx.args and ctx.args[0] and isinstance(ctx.args[0][0], StrExpr):
        return _field(ctx.type, ctx.args[0][0].value, ctx.api, ctx.default_return_type, ctx.context)
    return ctx.default_return_type


def _raw_draft(value: Type, api: Any) -> Type:
    proper = get_proper_type(value)
    if isinstance(proper, Instance):
        if proper.type.fullname == "wybthon.store.Draft":
            return proper.args[0]
        if proper.type.fullname == "wybthon.store.DraftList":
            return _named(api, "builtins.list", [_raw_draft(proper.args[0], api)])
    return value


def _draft_input(value: Type, api: Any) -> Type:
    proper = get_proper_type(value)
    if isinstance(proper, Instance):
        if proper.type.fullname in {"wybthon.store.Draft", "wybthon.store.DraftList"}:
            return UnionType.make_union([value, _raw_draft(value, api)])
        return proper.copy_modified(args=[_draft_input(argument, api) for argument in proper.args])
    if isinstance(proper, UnionType):
        return UnionType.make_union([_draft_input(item, api) for item in proper.items])
    return value


def _draft_list_signature(ctx: MethodSigContext) -> CallableType:
    return ctx.default_signature.copy_modified(
        arg_types=[_draft_input(value, ctx.api) for value in ctx.default_signature.arg_types]
    )


class WybthonPlugin(Plugin):
    """Transform component call signatures and nested store read types."""

    def get_method_signature_hook(self, fullname: str) -> Callable[[MethodSigContext], CallableType] | None:
        """Apply prop input types to component calls."""
        if fullname == "wybthon.component.Component.__call__":
            return _component_signature
        if fullname in {
            "wybthon.store.DraftList.append",
            "wybthon.store.DraftList.insert",
            "wybthon.store.DraftList.extend",
            "wybthon.store.DraftList.__setitem__",
        }:
            return _draft_list_signature
        return None

    def get_function_hook(self, fullname: str) -> Callable[[FunctionContext], Type] | None:
        """Preserve TypedDict and list element shapes at store creation."""
        return _store_created if fullname == "wybthon.store.create_store" else None

    def get_method_hook(self, fullname: str) -> Callable[[MethodContext], Type] | None:
        """Resolve literal store subscriptions."""
        return _item if fullname in {"wybthon.store.Store.__getitem__", "wybthon.store.Draft.__getitem__"} else None

    def get_attribute_hook(self, fullname: str) -> Callable[[AttributeContext], Type] | None:
        """Resolve optional attribute syntax against a TypedDict schema."""
        prefix, _, name = fullname.rpartition(".")
        if (
            prefix in {"wybthon.store.Store", "wybthon.store.Draft"}
            and not name.startswith("_")
            and name not in {"items", "keys", "values", "get", "update", "pop", "popitem", "setdefault", "clear"}
        ):

            def attribute(ctx: AttributeContext) -> Type:
                return _field(ctx.type, name, ctx.api, ctx.default_attr_type, ctx.context)

            return attribute
        return None


def plugin(version: str) -> type[Plugin]:
    """Mypy's plugin entry point."""
    return WybthonPlugin
