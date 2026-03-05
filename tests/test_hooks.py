"""Tests for the hooks system (use_state, use_effect, use_memo, use_ref, use_callback)."""

import importlib
import sys
import time
from types import ModuleType

import pytest

# Import wybthon BEFORE stubs so __init__.py runs with _IN_BROWSER=False
import wybthon as _wybthon_pkg  # noqa: F401

# --------------------------------------------------------------------------- #
# DOM stubs (same pattern as test_vdom_reorder.py / test_vdom_props.py)
# --------------------------------------------------------------------------- #


class _ClassList:
    def __init__(self):
        self._set = set()

    def add(self, name):
        self._set.add(name)

    def remove(self, name):
        self._set.discard(name)

    def contains(self, name):
        return name in self._set


class _Style:
    def __init__(self):
        self._props = {}

    def setProperty(self, name, value):
        self._props[name] = str(value)

    def removeProperty(self, name):
        self._props.pop(name, None)


class _Node:
    def __init__(self, tag=None, text=None):
        self.tag = tag
        self.nodeValue = text
        self._is_text = text is not None
        self._text = text
        self.parentNode = None
        self.childNodes = []
        self.attributes = {}
        self.classList = _ClassList()
        self.style = _Style()
        self.value = ""
        self.checked = False

    @property
    def nextSibling(self):
        if self.parentNode is None:
            return None
        try:
            idx = self.parentNode.childNodes.index(self)
        except ValueError:
            return None
        return self.parentNode.childNodes[idx + 1] if idx + 1 < len(self.parentNode.childNodes) else None

    def appendChild(self, node):
        if getattr(node, "parentNode", None) is not None:
            try:
                node.parentNode.childNodes.remove(node)
            except Exception:
                pass
        node.parentNode = self
        self.childNodes.append(node)
        return node

    def insertBefore(self, node, anchor):
        if getattr(node, "parentNode", None) is not None:
            try:
                node.parentNode.childNodes.remove(node)
            except Exception:
                pass
        node.parentNode = self
        if anchor is None:
            self.childNodes.append(node)
            return node
        try:
            idx = self.childNodes.index(anchor)
        except ValueError:
            self.childNodes.append(node)
            return node
        self.childNodes.insert(idx, node)
        return node

    def removeChild(self, node):
        try:
            self.childNodes.remove(node)
            node.parentNode = None
        except ValueError:
            pass
        return node

    def setAttribute(self, name, value):
        self.attributes[name] = str(value)

    def getAttribute(self, name):
        return self.attributes.get(name)

    def removeAttribute(self, name):
        self.attributes.pop(name, None)


class _Document:
    def __init__(self):
        self._listeners = {}

    def createElement(self, tag):
        return _Node(tag=tag)

    def createTextNode(self, text):
        return _Node(text=str(text))

    def addEventListener(self, event_type, proxy):
        self._listeners.setdefault(event_type, set()).add(proxy)

    def removeEventListener(self, event_type, proxy):
        s = self._listeners.get(event_type)
        if s is not None and proxy in s:
            s.remove(proxy)

    def querySelector(self, sel):
        return _Node(tag="div")

    def querySelectorAll(self, sel):
        return []


def _install_stubs():
    saved = {name: sys.modules.get(name) for name in ("js", "pyodide", "pyodide.ffi")}
    js_mod = ModuleType("js")
    js_mod.document = _Document()
    js_mod.fetch = lambda url: None
    sys.modules["js"] = js_mod

    pyodide = ModuleType("pyodide")
    ffi = ModuleType("pyodide.ffi")
    ffi.create_proxy = lambda fn: fn
    sys.modules["pyodide"] = pyodide
    sys.modules["pyodide.ffi"] = ffi
    setattr(pyodide, "ffi", ffi)
    return saved


def _restore(saved):
    for name, mod in saved.items():
        if mod is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = mod


def _reload_modules():
    """Reload wybthon submodules so they pick up the test stubs."""
    dom = importlib.import_module("wybthon.dom")
    importlib.reload(dom)
    events = importlib.import_module("wybthon.events")
    importlib.reload(events)
    component = importlib.import_module("wybthon.component")
    importlib.reload(component)
    context = importlib.import_module("wybthon.context")
    importlib.reload(context)
    reactivity = importlib.import_module("wybthon.reactivity")
    importlib.reload(reactivity)
    hooks = importlib.import_module("wybthon.hooks")
    importlib.reload(hooks)
    vdom = importlib.import_module("wybthon.vdom")
    importlib.reload(vdom)
    return vdom, hooks, dom


def _collect_texts(node):
    """Walk a stub _Node tree and collect all text node values."""
    out = []
    if getattr(node, "_is_text", False):
        out.append(node.nodeValue)
    for ch in getattr(node, "childNodes", []):
        out.extend(_collect_texts(ch))
    return out


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_use_state_initial_render():
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        render_log = []

        def Counter(props):
            count, _set = hooks.use_state(0)
            render_log.append(count)
            return vdom.h("p", {}, f"Count: {count}")

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(Counter, {}), root)

        assert render_log == [0]
        texts = _collect_texts(root.element)
        assert "Count: 0" in texts
    finally:
        _restore(saved)


def test_use_state_re_renders_on_set():
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        setter_ref = [None]
        render_log = []

        def Counter(props):
            count, set_count = hooks.use_state(0)
            setter_ref[0] = set_count
            render_log.append(count)
            return vdom.h("p", {}, f"Count: {count}")

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(Counter, {}), root)

        assert render_log == [0]
        assert "Count: 0" in _collect_texts(root.element)

        setter_ref[0](1)
        time.sleep(0.05)

        assert len(render_log) == 2
        assert render_log[-1] == 1
        assert "Count: 1" in _collect_texts(root.element)
    finally:
        _restore(saved)


def test_use_state_updater_function():
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        setter_ref = [None]
        render_log = []

        def Counter(props):
            count, set_count = hooks.use_state(10)
            setter_ref[0] = set_count
            render_log.append(count)
            return vdom.h("p", {}, f"{count}")

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(Counter, {}), root)
        assert render_log == [10]

        setter_ref[0](lambda prev: prev + 5)
        time.sleep(0.05)
        assert render_log[-1] == 15
    finally:
        _restore(saved)


def test_use_state_lazy_initializer():
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        init_calls = [0]

        def expensive_init():
            init_calls[0] += 1
            return 42

        values = []

        def MyComp(props):
            val, _ = hooks.use_state(expensive_init)
            values.append(val)
            return vdom.h("p", {}, str(val))

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(MyComp, {}), root)
        assert init_calls[0] == 1
        assert values == [42]
    finally:
        _restore(saved)


def test_use_effect_runs_after_mount():
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        log = []

        def MyComp(props):
            hooks.use_effect(lambda: log.append("mounted"), [])
            return vdom.h("p", {}, "hello")

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(MyComp, {}), root)

        assert "mounted" in log
    finally:
        _restore(saved)


def test_use_effect_cleanup_on_unmount():
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        log = []

        def MyComp(props):
            def setup():
                log.append("setup")
                return lambda: log.append("cleanup")

            hooks.use_effect(setup, [])
            return vdom.h("p", {}, "hello")

        root = dom.Element(node=_Node(tag="div"))
        tree = vdom.h(MyComp, {})
        vdom.render(tree, root)
        assert "setup" in log
        assert "cleanup" not in log

        vdom._unmount(tree)
        assert "cleanup" in log
    finally:
        _restore(saved)


def test_use_effect_no_deps_runs_every_render():
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        effect_runs = [0]
        setter_ref = [None]

        def MyComp(props):
            count, set_count = hooks.use_state(0)
            setter_ref[0] = set_count
            hooks.use_effect(lambda: effect_runs.__setitem__(0, effect_runs[0] + 1))
            return vdom.h("p", {}, f"{count}")

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(MyComp, {}), root)
        assert effect_runs[0] == 1

        setter_ref[0](1)
        time.sleep(0.05)
        assert effect_runs[0] == 2
    finally:
        _restore(saved)


def test_use_effect_empty_deps_runs_only_on_mount():
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        effect_runs = [0]
        setter_ref = [None]

        def MyComp(props):
            count, set_count = hooks.use_state(0)
            setter_ref[0] = set_count
            hooks.use_effect(lambda: effect_runs.__setitem__(0, effect_runs[0] + 1), [])
            return vdom.h("p", {}, f"{count}")

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(MyComp, {}), root)
        assert effect_runs[0] == 1

        setter_ref[0](1)
        time.sleep(0.05)
        # Effect should NOT have run again
        assert effect_runs[0] == 1
    finally:
        _restore(saved)


def test_use_effect_deps_re_runs_on_change():
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        effect_log = []
        setter_ref = [None]

        def MyComp(props):
            count, set_count = hooks.use_state(0)
            setter_ref[0] = set_count
            hooks.use_effect(lambda: effect_log.append(count), [count])
            return vdom.h("p", {}, f"{count}")

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(MyComp, {}), root)
        assert effect_log == [0]

        setter_ref[0](1)
        time.sleep(0.05)
        assert effect_log == [0, 1]

        # Same value → signal skips, no re-render, no effect
        setter_ref[0](1)
        time.sleep(0.05)
        assert effect_log == [0, 1]
    finally:
        _restore(saved)


def test_use_memo():
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        compute_calls = [0]
        setter_ref = [None]

        def MyComp(props):
            count, set_count = hooks.use_state(0)
            setter_ref[0] = set_count
            bucket = count // 2

            def expensive():
                compute_calls[0] += 1
                return bucket * 10

            result = hooks.use_memo(expensive, [bucket])
            return vdom.h("p", {}, f"{result}")

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(MyComp, {}), root)
        assert compute_calls[0] == 1
        assert "0" in _collect_texts(root.element)

        setter_ref[0](1)
        time.sleep(0.05)
        # bucket is still 0 → memo should NOT recompute
        assert compute_calls[0] == 1

        setter_ref[0](2)
        time.sleep(0.05)
        # bucket is now 1 → memo should recompute
        assert compute_calls[0] == 2
        assert "10" in _collect_texts(root.element)
    finally:
        _restore(saved)


def test_use_ref_persists_across_renders():
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        setter_ref = [None]
        ref_ids = []

        def MyComp(props):
            count, set_count = hooks.use_state(0)
            setter_ref[0] = set_count
            my_ref = hooks.use_ref("initial")
            ref_ids.append(id(my_ref))
            return vdom.h("p", {}, f"{my_ref.current}")

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(MyComp, {}), root)
        assert "initial" in _collect_texts(root.element)

        setter_ref[0](1)
        time.sleep(0.05)

        assert len(ref_ids) == 2
        assert ref_ids[0] == ref_ids[1]
    finally:
        _restore(saved)


def test_use_callback_stable_reference():
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        setter_ref = [None]
        callback_ids = []

        def MyComp(props):
            count, set_count = hooks.use_state(0)
            setter_ref[0] = set_count
            cb = hooks.use_callback(lambda: count, [])
            callback_ids.append(id(cb))
            return vdom.h("p", {}, f"{count}")

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(MyComp, {}), root)

        setter_ref[0](1)
        time.sleep(0.05)

        assert len(callback_ids) == 2
        assert callback_ids[0] == callback_ids[1]
    finally:
        _restore(saved)


def test_multiple_hooks_in_one_component():
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        setter_a_ref = [None]
        setter_b_ref = [None]

        def MyComp(props):
            a, set_a = hooks.use_state("hello")
            b, set_b = hooks.use_state(42)
            setter_a_ref[0] = set_a
            setter_b_ref[0] = set_b
            return vdom.h("div", {}, vdom.h("p", {}, a), vdom.h("p", {}, str(b)))

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(MyComp, {}), root)
        texts = _collect_texts(root.element)
        assert "hello" in texts
        assert "42" in texts

        setter_a_ref[0]("world")
        time.sleep(0.05)
        texts = _collect_texts(root.element)
        assert "world" in texts
        assert "42" in texts

        setter_b_ref[0](99)
        time.sleep(0.05)
        texts = _collect_texts(root.element)
        assert "world" in texts
        assert "99" in texts
    finally:
        _restore(saved)


def test_hooks_error_outside_component():
    """Hooks raise RuntimeError when called outside a component render."""
    from wybthon.hooks import use_effect, use_ref, use_state

    with pytest.raises(RuntimeError, match="Hooks can only be called inside"):
        use_state(0)

    with pytest.raises(RuntimeError, match="Hooks can only be called inside"):
        use_effect(lambda: None)

    with pytest.raises(RuntimeError, match="Hooks can only be called inside"):
        use_ref()


def test_nested_function_components_with_hooks():
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        child_setter_ref = [None]

        def Child(props):
            count, set_count = hooks.use_state(0)
            child_setter_ref[0] = set_count
            return vdom.h("span", {}, f"child:{count}")

        def Parent(props):
            label, _ = hooks.use_state("parent")
            return vdom.h("div", {}, vdom.h("p", {}, label), vdom.h(Child, {}))

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(Parent, {}), root)
        texts = _collect_texts(root.element)
        assert "parent" in texts
        assert "child:0" in texts

        child_setter_ref[0](5)
        time.sleep(0.05)
        texts = _collect_texts(root.element)
        assert "parent" in texts
        assert "child:5" in texts
    finally:
        _restore(saved)


def test_function_component_reads_signal_reactively():
    """Function components that read raw signals (without hooks) also re-render."""
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()
        reactivity = importlib.import_module("wybthon.reactivity")
        importlib.reload(reactivity)

        external_sig = reactivity.signal("initial")

        render_count = [0]

        def Display(props):
            render_count[0] += 1
            val = external_sig.get()
            return vdom.h("p", {}, val)

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(Display, {}), root)
        assert render_count[0] == 1
        assert "initial" in _collect_texts(root.element)

        external_sig.set("updated")
        time.sleep(0.05)
        assert render_count[0] == 2
        assert "updated" in _collect_texts(root.element)
    finally:
        _restore(saved)


# --------------------------------------------------------------------------- #
# use_layout_effect
# --------------------------------------------------------------------------- #


def test_use_layout_effect_runs_on_mount():
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        log = []

        def MyComp(props):
            hooks.use_layout_effect(lambda: log.append("layout_mounted"), [])
            return vdom.h("p", {}, "hello")

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(MyComp, {}), root)

        assert "layout_mounted" in log
    finally:
        _restore(saved)


def test_use_layout_effect_runs_before_regular_effects():
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        order = []

        def MyComp(props):
            hooks.use_effect(lambda: order.append("effect"), [])
            hooks.use_layout_effect(lambda: order.append("layout_effect"), [])
            return vdom.h("p", {}, "hello")

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(MyComp, {}), root)

        assert order.index("layout_effect") < order.index("effect")
    finally:
        _restore(saved)


def test_use_layout_effect_cleanup_on_unmount():
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        log = []

        def MyComp(props):
            def setup():
                log.append("layout_setup")
                return lambda: log.append("layout_cleanup")

            hooks.use_layout_effect(setup, [])
            return vdom.h("p", {}, "hello")

        root = dom.Element(node=_Node(tag="div"))
        tree = vdom.h(MyComp, {})
        vdom.render(tree, root)
        assert "layout_setup" in log
        assert "layout_cleanup" not in log

        vdom._unmount(tree)
        assert "layout_cleanup" in log
    finally:
        _restore(saved)


def test_use_layout_effect_deps_control_rerun():
    saved = _install_stubs()
    try:
        vdom, hooks, dom = _reload_modules()

        effect_log = []
        setter_ref = [None]

        def MyComp(props):
            count, set_count = hooks.use_state(0)
            setter_ref[0] = set_count
            hooks.use_layout_effect(lambda: effect_log.append(count), [count])
            return vdom.h("p", {}, f"{count}")

        root = dom.Element(node=_Node(tag="div"))
        vdom.render(vdom.h(MyComp, {}), root)
        assert effect_log == [0]

        setter_ref[0](1)
        time.sleep(0.05)
        assert effect_log == [0, 1]

        # Same value → no re-render → no layout effect
        setter_ref[0](1)
        time.sleep(0.05)
        assert effect_log == [0, 1]
    finally:
        _restore(saved)


def test_use_layout_effect_error_outside_component():
    """use_layout_effect raises RuntimeError when called outside a component."""
    import pytest

    from wybthon.hooks import use_layout_effect

    with pytest.raises(RuntimeError, match="Hooks can only be called inside"):
        use_layout_effect(lambda: None)
