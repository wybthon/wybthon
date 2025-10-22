"""Virtual DOM primitives, diffing, and rendering to real DOM elements."""

import re
from bisect import bisect_left
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Union, cast

from js import document

from .component import Component
from .context import Provider, pop_provider_value, push_provider_value
from .dom import Element
from .events import remove_all_for, set_handler
from .reactivity import Computation, Signal, effect, signal

__all__ = [
    "VNode",
    "h",
    "render",
    "ErrorBoundary",
    "Suspense",
]

PropsDict = Dict[str, Any]
ChildType = Union["VNode", str]


@dataclass
class VNode:
    """Virtual node representing an element, text, or component subtree."""

    tag: Optional[Union[str, Callable[..., Any]]]
    props: PropsDict = field(default_factory=dict)
    children: List[ChildType] = field(default_factory=list)
    key: Optional[Union[str, int]] = None
    el: Optional[Element] = None
    component_instance: Optional[Component] = None
    subtree: Optional["VNode"] = None
    render_effect: Optional[Computation] = None


class ErrorBoundary(Component):
    """Component that catches errors in its subtree and renders a fallback."""

    def __init__(self, props: Dict[str, Any]) -> None:
        super().__init__(props)
        self._error: Signal[Optional[Any]] = signal(None)
        # Track a token derived from `reset_keys`/`reset_key` to auto-clear error when it changes
        self._last_reset_token: str = ""

    def render(self):
        # Auto-reset when reset_keys/reset_key token changes
        try:
            rk = self.props.get("reset_keys") if "reset_keys" in self.props else self.props.get("reset_key")
            if isinstance(rk, (list, tuple)):
                token = repr(tuple(rk))
            else:
                token = repr(rk)
        except Exception:
            token = ""

        current_err = self._error.get()
        if token != self._last_reset_token and current_err is not None:
            try:
                self._error.set(None)
                current_err = None
            except Exception:
                pass
        self._last_reset_token = token

        err = current_err
        if err is not None:
            fb = self.props.get("fallback")
            if callable(fb):
                try:
                    # Prefer calling with (error, reset) for ergonomics; fall back to (error)
                    try:
                        vnode = fb(err, self.reset)
                    except TypeError:
                        vnode = fb(err)
                except Exception:
                    vnode = _to_text_vnode("Error rendering fallback")
            else:
                vnode = (
                    fb
                    if isinstance(fb, VNode)
                    else _to_text_vnode(str(fb) if fb is not None else "Something went wrong.")
                )
            if not isinstance(vnode, VNode):
                vnode = _to_text_vnode(vnode)
            return vnode
        children = self.props.get("children", [])
        if not isinstance(children, list):
            children = [children]
        return h("div", {}, *children)

    # Public API to reset the boundary
    def reset(self) -> None:
        """Clear the current error and re-render children."""
        self._error.set(None)


def _to_text_vnode(value: Any) -> VNode:
    """Convert arbitrary value to a text VNode."""
    return VNode(tag="_text", props={"nodeValue": "" if value is None else str(value)}, children=[])


class Suspense(Component):
    """Render a fallback while one or more resources are loading.

    Props:
      - resources | resource: Resource or list of Resources (objects exposing `.loading.get()`)
      - fallback: VNode | str | callable returning VNode/str
      - keep_previous: bool (default False) – when True, keep children visible after first
        successful load even if a subsequent reload is in-flight.
    """

    def __init__(self, props: Dict[str, Any]) -> None:
        super().__init__(props)
        self._has_completed_once: bool = False

    def _normalize_resources(self) -> List[Any]:
        """Normalize the resources prop(s) to a flat list."""
        res = self.props.get("resources")
        if res is None and "resource" in self.props:
            res = [self.props.get("resource")]
        if res is None:
            return []
        if not isinstance(res, list):
            res = [res]
        return [r for r in res if r is not None]

    def _is_loading(self, resources: List[Any]) -> bool:
        """Return True if any resource reports loading=True."""
        # Read loading signals to subscribe the render effect to future changes
        for r in resources:
            try:
                loading_sig = getattr(r, "loading", None)
                if loading_sig is None:
                    continue
                if callable(getattr(loading_sig, "get", None)) and loading_sig.get():
                    return True
            except Exception:
                # Ignore malformed resource-like objects
                continue
        return False

    def _render_children(self) -> VNode:
        """Render and return the children inside a div container."""
        children = self.props.get("children", [])
        if not isinstance(children, list):
            children = [children]
        return h("div", {}, *children)

    def _render_fallback(self) -> VNode:
        """Render the fallback content as a VNode."""
        fb = self.props.get("fallback")
        vnode: Any
        if callable(fb):
            try:
                vnode = fb()
            except Exception:
                vnode = _to_text_vnode("Loading...")
        else:
            vnode = fb if isinstance(fb, VNode) else _to_text_vnode("" if fb is None else str(fb))
        if not isinstance(vnode, VNode):
            vnode = _to_text_vnode(vnode)
        return vnode

    def render(self):
        resources = self._normalize_resources()
        if not resources:
            return self._render_children()
        keep_previous = bool(self.props.get("keep_previous", False))
        is_loading = self._is_loading(resources)
        if is_loading:
            if keep_previous and self._has_completed_once:
                return self._render_children()
            return self._render_fallback()
        # Mark that at least one successful completion happened
        self._has_completed_once = True
        return self._render_children()


def _flatten_children(items: Iterable[Any]) -> List[Any]:
    """Flatten nested child lists into a single list while dropping Nones."""
    out: List[Any] = []
    for item in items:
        if item is None:
            continue
        if isinstance(item, (list, tuple)):
            out.extend(_flatten_children(item))
        else:
            out.append(item)
    return out


def h(tag: Optional[Union[str, Callable[..., Any]]], props: Optional[PropsDict] = None, *children: Any) -> VNode:
    """Create a VNode from a tag, props, and children (component-aware)."""
    props = props or {}
    key = props.get("key") if "key" in props else None
    flat_children = _flatten_children(children)
    # For component nodes, pass children via props
    if callable(tag):
        if "children" not in props:
            props["children"] = list(flat_children)
        vnode_children: List[ChildType] = []
    else:
        vnode_children = list(flat_children)
    return VNode(tag=tag, props=props, children=vnode_children, key=key)


_container_registry: Dict[int, VNode] = {}


def render(vnode: VNode, container: Union[Element, str]) -> Element:
    """Render a VNode tree into a container `Element` or CSS selector."""
    if isinstance(container, str):
        container_el = Element(container, existing=True)
    else:
        container_el = container
    prev = _container_registry.get(id(container_el.element))
    _patch(prev, vnode, container_el)
    _container_registry[id(container_el.element)] = vnode
    return container_el


def _create_dom(vnode: VNode) -> Element:
    """Create a real DOM element for an element/text VNode and its subtree."""
    if vnode.tag == "_text":
        node = document.createTextNode(vnode.props.get("nodeValue", ""))
        el = Element(node=node)
        vnode.el = el
        return el

    assert vnode.tag is not None, "VNode.tag must not be None for element nodes"
    assert isinstance(vnode.tag, str), "_create_dom only handles element or text nodes"
    el = Element(vnode.tag)
    _apply_props(el, {}, vnode.props)
    # Normalize once and persist so future diffs have stable VNode references with el
    norm_children = _normalize_children(vnode.children)
    vnode.children = cast(List[ChildType], norm_children)
    for child in norm_children:
        _mount(child, el)
    vnode.el = el
    return el


def _mount(vnode: Union[VNode, str], container: Element, anchor: Any = None) -> Element:
    """Mount a VNode (or string) into the container, returning its element."""
    if not isinstance(vnode, VNode):
        vnode = _to_text_vnode(vnode)
    # Component nodes
    if callable(vnode.tag):
        comp_ctor = vnode.tag
        # Class component
        if isinstance(comp_ctor, type) and issubclass(comp_ctor, Component):
            instance = comp_ctor(vnode.props)
            vnode.component_instance = instance

            def run_render():
                try:
                    if isinstance(instance, Provider):
                        ctx = instance.props.get("context")
                        value = instance.props.get("value")
                        children = instance.props.get("children", [])
                        push_provider_value(ctx, value)
                        try:
                            next_sub = h("div", {}, *children)
                        finally:
                            pop_provider_value()
                    else:
                        next_sub = instance.render()

                    if not isinstance(next_sub, VNode):
                        next_sub = _to_text_vnode(next_sub)
                    prev_sub = vnode.subtree
                    vnode.subtree = next_sub
                    if prev_sub is None:
                        mounted_el = _mount(next_sub, container, anchor)
                        vnode.el = mounted_el
                    else:
                        _patch(prev_sub, next_sub, container)
                        vnode.el = next_sub.el
                except Exception as e:
                    if isinstance(instance, ErrorBoundary):
                        try:
                            instance._error.set(e)
                        except Exception:
                            pass
                        # Notify via on_error callback if provided
                        try:
                            handler = instance.props.get("on_error")
                            if callable(handler):
                                handler(e)
                        except Exception:
                            pass
                        try:
                            fb_sub = instance.render()
                            if not isinstance(fb_sub, VNode):
                                fb_sub = _to_text_vnode(fb_sub)
                        except Exception:
                            fb_sub = _to_text_vnode("Error in fallback")
                        prev_sub = vnode.subtree
                        vnode.subtree = fb_sub
                        if prev_sub is None or getattr(prev_sub, "el", None) is None:
                            mounted_el = _mount(fb_sub, container, anchor)
                            vnode.el = mounted_el
                        else:
                            _patch(prev_sub, fb_sub, container)
                            vnode.el = fb_sub.el
                    else:
                        print("Component render error:", e)
                        raise

            vnode.render_effect = effect(run_render)
        else:
            # Function component
            sub_tree = comp_ctor(vnode.props)  # type: ignore[call-arg]
            if not isinstance(sub_tree, VNode):
                sub_tree = _to_text_vnode(sub_tree)
            vnode.subtree = sub_tree
            mounted = _mount(sub_tree, container, anchor)
            vnode.el = mounted
        if vnode.component_instance is not None:
            try:
                vnode.component_instance.on_mount()
            except Exception:
                pass
        return vnode.el
    # Element or text nodes
    el = _create_dom(vnode)
    if anchor is None:
        container.element.appendChild(el.element)
    else:
        container.element.insertBefore(el.element, anchor)
    return el


def _unmount(vnode: VNode) -> None:
    """Unmount a VNode and dispose associated resources and effects."""
    if vnode.el is None:
        return
    try:
        # Remove delegated handlers tracking for this node
        remove_all_for(vnode.el)
        vnode.el.cleanup()
    except Exception:
        pass
    if vnode.component_instance is not None:
        try:
            vnode.component_instance._run_cleanups()
            vnode.component_instance.on_unmount()
        except Exception:
            pass
    if vnode.render_effect is not None:
        try:
            vnode.render_effect.dispose()
        except Exception:
            pass
    if vnode.subtree is not None:
        _unmount(vnode.subtree)
    for child in _normalize_children(vnode.children):
        if isinstance(child, VNode):
            _unmount(child)
    if vnode.el.element.parentNode is not None:
        vnode.el.element.parentNode.removeChild(vnode.el.element)


def _normalize_children(children: List[ChildType]) -> List[VNode]:
    """Normalize mixed children into a list of VNodes (converting strings)."""
    out: List[VNode] = []
    for ch in children:
        if isinstance(ch, VNode):
            out.append(ch)
        else:
            out.append(_to_text_vnode(ch))
    return out


def _same_type(a: VNode, b: VNode) -> bool:
    """Return True when both VNodes represent the same tag/component type."""
    return a.tag == b.tag


def _patch(old: Optional[VNode], new: VNode, container: Element) -> None:
    """Patch `old` into `new` by mutating DOM as needed within the container."""
    if old is None:
        _mount(new, container)
        return

    if not _same_type(old, new):
        anchor = old.el.element.nextSibling if (old.el is not None) else None
        _unmount(old)
        _mount(new, container, anchor)
        return

    # Text node fast-path
    if old.tag == "_text" and new.tag == "_text":
        new.el = old.el
        if new.el is not None:
            old_text = old.props.get("nodeValue", "")
            new_text = new.props.get("nodeValue", "")
            if old_text != new_text:
                try:
                    new.el.element.nodeValue = new_text
                except Exception:
                    pass
        return

    assert old.el is not None
    new.el = old.el
    # Component nodes
    if callable(new.tag):
        # Class component
        if isinstance(new.tag, type) and issubclass(new.tag, Component):
            instance = old.component_instance or new.tag(new.props)
            prev_props = getattr(instance, "props", {})
            instance.props = new.props
            new.component_instance = instance
            try:
                # Special-case Provider to ensure context push/pop and VNode children wrapper
                if isinstance(instance, Provider):
                    ctx = instance.props.get("context")
                    value = instance.props.get("value")
                    children = instance.props.get("children", [])
                    push_provider_value(ctx, value)
                    try:
                        next_sub = h("div", {}, *children)
                    finally:
                        pop_provider_value()
                else:
                    next_sub = instance.render()
                    if not isinstance(next_sub, VNode):
                        next_sub = _to_text_vnode(next_sub)
                prev_sub = old.subtree
                new.subtree = next_sub
                if prev_sub is None:
                    _mount(next_sub, container)
                else:
                    _patch(prev_sub, next_sub, container)
                try:
                    instance.on_update(prev_props)
                except Exception:
                    pass
                return
            except Exception as e:
                if isinstance(instance, ErrorBoundary):
                    try:
                        instance._error.set(e)
                    except Exception:
                        pass
                    # Notify via on_error callback if provided
                    try:
                        handler = instance.props.get("on_error")
                        if callable(handler):
                            handler(e)
                    except Exception:
                        pass
                    try:
                        fb_sub = instance.render()
                        if not isinstance(fb_sub, VNode):
                            fb_sub = _to_text_vnode(fb_sub)
                    except Exception:
                        fb_sub = _to_text_vnode("Error in fallback")
                    prev_sub = old.subtree
                    new.subtree = fb_sub
                    if prev_sub is None or getattr(prev_sub, "el", None) is None:
                        _mount(fb_sub, container)
                    else:
                        _patch(prev_sub, fb_sub, container)
                    return
                print("Component render error:", e)
                raise
        else:
            # Function component
            func_sub = new.tag(new.props)  # type: ignore[call-arg]
            if not isinstance(func_sub, VNode):
                func_sub = _to_text_vnode(func_sub)
            prev_sub = old.subtree
            new.subtree = func_sub
            if prev_sub is None:
                _mount(func_sub, container)
            else:
                _patch(prev_sub, func_sub, container)
            return

    # Element nodes
    _apply_props(new.el, old.props, new.props)
    _patch_children(old, new)


def _patch_children(old: VNode, new: VNode) -> None:
    """Diff and apply changes for a node's children using key-aware reordering."""
    parent = new.el
    assert parent is not None

    # Old children should already be normalized VNodes with el set
    old_children = _normalize_children(old.children)
    # Normalize new children now and persist on the new vnode
    new_children = _normalize_children(new.children)
    new.children = cast(List[ChildType], new_children)

    # 1) Match new children to old children (by key first, then by type for unkeyed)
    old_key_to_index: Dict[Union[str, int], int] = {}
    for i, ch in enumerate(old_children):
        if ch.key is not None:
            old_key_to_index[ch.key] = i

    used_old: List[bool] = [False] * len(old_children)
    sources: List[int] = [-1] * len(new_children)

    for i, new_child in enumerate(new_children):
        if new_child.key is not None and new_child.key in old_key_to_index:
            idx = old_key_to_index[new_child.key]
            sources[i] = idx
            used_old[idx] = True
            # Patch existing matched nodes to sync props/children
            _patch(old_children[idx], new_child, parent)
        else:
            # Fallback: match first still-available old child of same type and without key
            for j, oc in enumerate(old_children):
                if used_old[j]:
                    continue
                if oc.key is None and _same_type(oc, new_child):
                    sources[i] = j
                    used_old[j] = True
                    _patch(oc, new_child, parent)
                    break

    # 2) Compute LIS over the matched old indices to minimize moves
    n = len(new_children)
    tails: List[int] = []
    tails_idx: List[int] = []
    prev_idx: List[int] = [-1] * n
    for i in range(n):
        s = sources[i]
        if s == -1:
            continue
        pos = bisect_left(tails, s)
        if pos == len(tails):
            tails.append(s)
            tails_idx.append(i)
        else:
            tails[pos] = s
            tails_idx[pos] = i
        prev_idx[i] = tails_idx[pos - 1] if pos > 0 else -1

    lis_set = set()
    k = tails_idx[-1] if tails_idx else -1
    while k != -1:
        lis_set.add(k)
        k = prev_idx[k]

    # 3) Walk from right to left to move existing nodes and mount new ones
    next_anchor_node = None  # DOM node to insert before
    for i in range(n - 1, -1, -1):
        new_child = new_children[i]
        s = sources[i]
        if s == -1:
            # Brand new node; mount before the current anchor
            try:
                mounted_el = _mount(new_child, parent, next_anchor_node)
                next_anchor_node = mounted_el.element
            except Exception:
                pass
        else:
            new_el = new_child.el
            if new_el is not None:
                try:
                    # Move only if this index is not in LIS (i.e., out of order)
                    if i not in lis_set:
                        parent.element.insertBefore(new_el.element, next_anchor_node)
                except Exception:
                    pass
                next_anchor_node = new_el.element

    # 4) Unmount any old children that were not matched at all
    for j, oc in enumerate(old_children):
        if not used_old[j]:
            _unmount(oc)


def _is_event_prop(name: str) -> bool:
    """Return True if a prop name is an event handler prop like on_click."""
    return name.startswith("on_") or name.startswith("on")


def _event_name_from_prop(name: str) -> str:
    """Map on_click/onClick style props to a DOM event name."""
    if name.startswith("on_"):
        return name[3:]
    if name.startswith("on"):
        return name[2:].lower()
    return name


CAMEL_TO_KEBAB = re.compile(r"(?<!^)(?=[A-Z])")


def _to_kebab(name: str) -> str:
    """Convert camelCase style property names to kebab-case."""
    return CAMEL_TO_KEBAB.sub("-", name).lower()


def _apply_props(el: Element, old_props: PropsDict, new_props: PropsDict) -> None:
    """Apply prop diffs to a concrete DOM element, including events and styles."""
    for name, old_val in list(old_props.items()):
        if name == "key":
            continue
        if name not in new_props:
            if _is_event_prop(name):
                set_handler(el, name, None)
            elif name in ("class", "className"):
                el.set_attr("class", "")
            elif name == "style":
                style_obj = el.element.style
                if isinstance(old_val, dict):
                    for sk in old_val.keys():
                        style_obj.removeProperty(_to_kebab(sk))
            elif name == "dataset":
                if isinstance(old_val, dict):
                    for dk in old_val.keys():
                        el.remove_attr(f"data-{dk}")
            elif name == "value":
                try:
                    el.element.value = ""
                except Exception:
                    el.remove_attr("value")
            elif name == "checked":
                try:
                    el.element.checked = False
                except Exception:
                    el.remove_attr("checked")
            else:
                el.remove_attr(name)

    for name, new_val in new_props.items():
        if name == "key":
            continue
        if _is_event_prop(name):
            old_handler = old_props.get(name)
            if old_handler is new_val:
                continue
            set_handler(el, name, new_val if callable(new_val) else None)
            continue

        if name in ("class", "className"):
            class_str: str
            if new_val is None:
                class_str = ""
            elif isinstance(new_val, str):
                class_str = new_val
            elif isinstance(new_val, (list, tuple)):
                class_str = " ".join(str(x) for x in new_val if x)
            else:
                class_str = str(new_val)
            el.set_attr("class", class_str)
            continue

        if name == "style":
            style_obj = el.element.style
            old_styles = old_props.get("style") if isinstance(old_props.get("style"), dict) else {}
            if isinstance(new_val, dict):
                if isinstance(old_styles, dict):
                    for sk in old_styles.keys():
                        if sk not in new_val:
                            style_obj.removeProperty(_to_kebab(sk))
                for sk, sv in new_val.items():
                    style_obj.setProperty(_to_kebab(sk), str(sv))
            else:
                # Clear previous styles when style is None or non-dict
                if isinstance(old_styles, dict):
                    for sk in old_styles.keys():
                        style_obj.removeProperty(_to_kebab(sk))
            continue

        if name == "dataset":
            old_ds = old_props.get("dataset") if isinstance(old_props.get("dataset"), dict) else {}
            if isinstance(new_val, dict):
                if isinstance(old_ds, dict):
                    for dk in old_ds.keys():
                        if dk not in new_val:
                            el.remove_attr(f"data-{dk}")
                for dk, dv in new_val.items():
                    el.set_attr(f"data-{dk}", dv)
            else:
                # Clear previous dataset when dataset is None or non-dict
                if isinstance(old_ds, dict):
                    for dk in old_ds.keys():
                        el.remove_attr(f"data-{dk}")
            continue

        # Controlled form properties: prefer DOM properties over attributes
        if name == "value":
            try:
                el.element.value = "" if new_val is None else str(new_val)
            except Exception:
                el.set_attr("value", "" if new_val is None else str(new_val))
            continue

        if name == "checked":
            try:
                el.element.checked = bool(new_val)
            except Exception:
                if new_val:
                    el.set_attr("checked", "checked")
                else:
                    el.remove_attr("checked")
            continue

        el.set_attr(name, new_val)
