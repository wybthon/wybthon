"""Guarded Python recipes for repeatedly mounted VDOM template shapes.

The ordinary serializer validates HTML eligibility first. A recipe then checks
the complete shape of each new VNode tree and extracts its current bindings.
It never evaluates a reactive expression or retains an instance's values.
Generated source contains only framework expressions and numeric indexes;
tags, prop names, and static values live in a separate constants table.
"""

from __future__ import annotations

from typing import Any, Callable

from .props import KIND_EVENT, KIND_REF, KIND_SKIP, binding_value, prop_kind
from .reactivity._core import is_accessor
from .vnode import VNode, hole


def specialize(vnode: VNode, html: str) -> Callable[[VNode], Any] | None:
    """Build a bounded, fully guarded extractor from a validated template."""
    from .template import (
        BIND_EVENT,
        BIND_PROP,
        BIND_REACTIVE,
        BIND_REF,
        BIND_TEXT,
        NODE_HOLE,
        NODE_MOUNT,
        NODE_STATIC,
        MountPlan,
        _static_attribute,
    )

    constants: list[Any] = []
    lines = ["def extract(n0):"]
    order: list[str] = []
    bindings: list[str] = []
    count = 0

    def const(value: Any) -> str:
        constants.append(value)
        return f"C[{len(constants) - 1}]"

    def emit(code: str) -> None:
        lines.append(f"    {code}")

    def guard(condition: str) -> None:
        emit(f"if {condition}: return None")

    def walk(node: VNode, parent: str = "None", child_index: int = -1) -> None:
        nonlocal count
        number = count
        count += 1
        if count > 128:
            raise OverflowError
        n, p, c = f"n{number}", f"p{number}", f"c{number}"
        if child_index >= 0:
            emit(f"{n} = {parent}.children[{child_index}]")
        tag = node.tag
        if tag == "_text":
            emit(f"if type({n}) in (str, int, float):")
            emit(f"    {n} = VNode('_text', {{'nodeValue': str({n})}})")
            emit(f"    {parent}.children[{child_index}] = {n}")
        elif tag == "_hole":
            emit(f"if type({n}) is not VNode:")
            emit(f"    if not is_accessor({n}): return None")
            emit(f"    {n} = hole({n})")
            emit(f"    {parent}.children[{child_index}] = {n}")
        guard(f"type({n}) is not VNode")
        kind = NODE_STATIC
        if tag == "_hole":
            kind = NODE_HOLE
        elif not isinstance(tag, str) or tag.startswith("_") and tag != "_text":
            kind = NODE_MOUNT
        order.append(f"({kind}, {n}, {parent})")
        if kind == NODE_MOUNT:
            # Anonymous fragments flatten; all other dynamic children occupy
            # one placeholder regardless of their eventual rendered shape.
            guard(f"isinstance({n}.tag, str) and (not {n}.tag.startswith('_') or {n}.tag in ('_text', '_hole'))")
            guard(f"{n}.tag == '_fragment' and {n}.owner_scope is None and {n}.key is None")
            return
        guard(f"{n}.tag != {const(tag)}")
        if kind == NODE_HOLE:
            return
        if tag == "_text":
            bindings.append(f"({n}, {BIND_TEXT}, '', str({n}.props.get('nodeValue', '')))")
            return
        emit(f"{p} = {n}.props")
        guard(f"type({p}) is not dict")
        guard(f"tuple({p}) != {const(tuple(node.props))}" if node.props else p)
        for name, value in node.props.items():
            prop_type = prop_kind(name)
            if prop_type == KIND_SKIP:
                continue
            name_ref = const(name)
            v = f"{p}[{name_ref}]"
            if prop_type == KIND_REF:
                # A None ref is harmless when replayed through attach_ref.
                binding = BIND_REF
            elif prop_type == KIND_EVENT:
                binding = BIND_EVENT
            elif binding_value(name, value) is not None:
                getter = f"g{len(bindings)}"
                emit(f"{getter} = binding_value({name_ref}, {v})")
                guard(f"{getter} is None")
                v, binding = getter, BIND_REACTIVE
            elif _static_attribute(name, value):
                guard(f"type({v}) is not {const(type(value))} or {v} != {const(value)}")
                continue
            else:
                guard(f"binding_value({name_ref}, {v}) is not None or static_attribute({name_ref}, {v})")
                binding = BIND_PROP
            bindings.append(f"({n}, {binding}, {name_ref}, {v})")
        emit(f"{c} = {n}.children")
        guard(f"type({c}) is not list")
        guard(f"len({c}) != {len(node.children)}")
        for index, child in enumerate(node.children):
            walk(child, n, index)

    try:
        walk(vnode)
    except OverflowError:
        return None
    emit(f"return MountPlan(HTML, [{', '.join(order)}], [{', '.join(bindings)}])")
    namespace: dict[str, Any] = {
        "C": tuple(constants),
        "HTML": html,
        "VNode": VNode,
        "MountPlan": MountPlan,
        "hole": hole,
        "is_accessor": is_accessor,
        "binding_value": binding_value,
        "static_attribute": _static_attribute,
    }
    exec(compile("\n".join(lines), "<wybthon template>", "exec"), namespace)
    return namespace["extract"]
