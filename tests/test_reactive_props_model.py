"""Tests for the new fully-reactive props model.

These tests cover the headline features of the unified component model:

* Every ``@component`` parameter is bound to a reactive accessor.
* Passing the accessor as a child auto-creates a reactive hole.
* Single-positional-param components receive the ``ReactiveProps`` proxy.
* ``Provider`` context values are signal-backed and update fine-grainedly.
* ``create_signal`` defaults to **value equality** (``==``) with an
  identity (``is``) fast-path; SolidJS-style identity-only semantics
  are an explicit opt-in via ``equals=lambda a, b: a is b``.
* ``untrack`` silences the destructured-prop dev warning.
"""

from __future__ import annotations

import time

from conftest import collect_texts

# ---------------------------------------------------------------------------
# Auto-hole behaviour
# ---------------------------------------------------------------------------


def test_prop_accessor_passed_into_tree_is_auto_hole(wyb, root_element):
    """Passing a prop accessor as a child creates a reactive hole."""
    vdom, comp_mod, reactivity = wyb["vdom"], wyb["component"], wyb["reactivity"]

    parent_setter = [None]
    child_runs = [0]

    @comp_mod.component
    def Greet(name="anon"):
        child_runs[0] += 1
        return vdom.h("p", {}, "Hello, ", name, "!")

    @comp_mod.component
    def Parent():
        n, set_n = reactivity.create_signal("Alice")
        parent_setter[0] = set_n
        return vdom.h(Greet, {"name": n})

    vdom.render(vdom.h(Parent, {}), root_element)
    assert "Alice" in collect_texts(root_element.element)
    assert child_runs[0] == 1

    parent_setter[0]("Bob")
    time.sleep(0.05)

    assert "Bob" in collect_texts(root_element.element)
    assert child_runs[0] == 1, "child setup must run only once"


def test_prop_accessor_can_be_called_for_static_value(wyb, root_element):
    """Calling an accessor at setup gives a static (untracked) snapshot."""
    vdom, comp_mod, reactivity = wyb["vdom"], wyb["component"], wyb["reactivity"]

    parent_setter = [None]

    @comp_mod.component
    def Greet(name="anon"):
        snapshot = reactivity.untrack(name)
        return vdom.h("p", {}, f"Hello, {snapshot}!")

    @comp_mod.component
    def Parent():
        n, set_n = reactivity.create_signal("Alice")
        parent_setter[0] = set_n
        return vdom.h(Greet, {"name": n})

    vdom.render(vdom.h(Parent, {}), root_element)
    assert "Hello, Alice!" in collect_texts(root_element.element)

    parent_setter[0]("Bob")
    time.sleep(0.05)

    assert "Hello, Alice!" in collect_texts(root_element.element)


def test_proxy_mode_for_single_positional_param():
    """A component with one positional param receives the ``ReactiveProps`` proxy."""
    from wybthon.component import component
    from wybthon.reactivity import ReactiveProps

    captured = {}

    @component
    def Card(props):
        captured["props"] = props
        captured["title"] = props.title()
        captured["x"] = props["x"]()

    Card({"title": "Hi", "x": 42})

    assert isinstance(captured["props"], ReactiveProps)
    assert captured["title"] == "Hi"
    assert captured["x"] == 42


def test_props_accept_static_value_or_getter(wyb, root_element):
    """Children read the value the same way regardless of how the parent passed it."""
    vdom, comp_mod, reactivity = wyb["vdom"], wyb["component"], wyb["reactivity"]

    @comp_mod.component
    def Show(value=""):
        return vdom.h("p", {}, "v=", value)

    src, set_src = reactivity.create_signal("dynamic")

    vdom.render(vdom.h("div", {}, vdom.h(Show, {"value": "static"})), root_element)
    assert "v=static" in "".join(collect_texts(root_element.element))

    vdom.render(vdom.h("div", {}, vdom.h(Show, {"value": src})), root_element)
    txt = "".join(collect_texts(root_element.element))
    assert "v=dynamic" in txt

    set_src("updated")
    time.sleep(0.05)
    assert "updated" in "".join(collect_texts(root_element.element))


# ---------------------------------------------------------------------------
# Reactive context
# ---------------------------------------------------------------------------


def test_provider_value_updates_fine_grainedly(wyb, root_element):
    """Updating Provider's value re-runs only consumers, not the whole subtree."""
    vdom, comp_mod, reactivity = wyb["vdom"], wyb["component"], wyb["reactivity"]
    from wybthon.context import Provider, create_context, use_context

    Theme = create_context("light")
    consumer_runs = [0]
    parent_setter = [None]

    @comp_mod.component
    def Consumer():
        consumer_runs[0] += 1
        return vdom.h("p", {}, "theme=", lambda: use_context(Theme))

    @comp_mod.component
    def App():
        theme, set_theme = reactivity.create_signal("light")
        parent_setter[0] = set_theme
        return vdom.h(
            Provider,
            {"context": Theme, "value": theme},
            vdom.h(Consumer, {}),
        )

    vdom.render(vdom.h(App, {}), root_element)
    assert "theme=light" in "".join(collect_texts(root_element.element))
    assert consumer_runs[0] == 1

    parent_setter[0]("dark")
    time.sleep(0.05)

    assert "theme=dark" in "".join(collect_texts(root_element.element))
    assert consumer_runs[0] == 1, "consumer body must run only once; hole updates the DOM"


def test_provider_static_value_still_propagates(wyb, root_element):
    """Provider with a literal value still works the same."""
    vdom, comp_mod = wyb["vdom"], wyb["component"]
    from wybthon.context import Provider, create_context, use_context

    Theme = create_context("light")

    @comp_mod.component
    def Consumer():
        return vdom.h("p", {}, "t=", lambda: use_context(Theme))

    vdom.render(
        vdom.h(Provider, {"context": Theme, "value": "dark"}, vdom.h(Consumer, {})),
        root_element,
    )
    assert "t=dark" in "".join(collect_texts(root_element.element))


# ---------------------------------------------------------------------------
# Signal equality semantics
# ---------------------------------------------------------------------------


def test_signal_default_value_equality_skips_same_reference():
    """Default ``equals`` is value equality with an identity fast-path."""
    from wybthon.reactivity import create_effect, create_signal

    log = []
    items = [1, 2, 3]
    s, set_s = create_signal(items)
    create_effect(lambda: log.append(s()))

    assert log == [items]

    set_s(items)
    time.sleep(0.05)
    assert log == [items], "same reference → must skip via identity fast-path"


def test_signal_default_value_equality_skips_equal_value():
    """A new container with value-equal contents skips notification by default.

    This is the most Python-natural behavior: re-setting a logically
    unchanged value is a no-op.  Users who want SolidJS-style identity
    semantics opt in explicitly via ``equals=lambda a, b: a is b``.
    """
    from wybthon.reactivity import create_effect, create_signal

    log = []
    s, set_s = create_signal([1, 2, 3])
    create_effect(lambda: log.append(s()))

    assert len(log) == 1

    set_s([1, 2, 3])
    time.sleep(0.05)
    assert len(log) == 1, "value-equal new object → must skip by default"

    set_s([1, 2, 4])
    time.sleep(0.05)
    assert len(log) == 2, "value-different → must notify"


def test_signal_identity_equality_via_explicit_equals():
    """SolidJS-style identity-only semantics opt-in via custom comparator."""
    from wybthon.reactivity import create_effect, create_signal

    log = []
    s, set_s = create_signal([1, 2, 3], equals=lambda a, b: a is b)
    create_effect(lambda: log.append(s()))

    assert len(log) == 1

    set_s([1, 2, 3])
    time.sleep(0.05)
    assert len(log) == 2, "different identity → must notify under identity-equals"


def test_signal_equals_true_is_value_equality():
    """``equals=True`` is the same as the default (value equality)."""
    from wybthon.reactivity import create_effect, create_signal

    log = []
    s, set_s = create_signal({"a": 1}, equals=True)
    create_effect(lambda: log.append(s()))

    assert len(log) == 1

    set_s({"a": 1})
    time.sleep(0.05)
    assert len(log) == 1, "equals=True must skip on value-equal set"


def test_signal_equals_false_always_notifies():
    """``equals=False`` forces notification on every set."""
    from wybthon.reactivity import create_effect, create_signal

    log = []
    s, set_s = create_signal(0, equals=False)
    create_effect(lambda: log.append(s()))

    assert len(log) == 1
    set_s(0)
    time.sleep(0.05)
    assert len(log) == 2


# ---------------------------------------------------------------------------
# Dev-mode warnings
# ---------------------------------------------------------------------------


def test_destructured_prop_warning_fires(wyb, root_element, capsys):
    """Reading a prop accessor at setup triggers the dev-mode warning."""
    vdom, comp_mod = wyb["vdom"], wyb["component"]
    from wybthon._warnings import _reset_warning_dedupe, set_dev_mode

    set_dev_mode(True)
    _reset_warning_dedupe()

    @comp_mod.component
    def Loose(name="anon"):
        _ = name()
        return vdom.h("p", {}, "x")

    vdom.render(vdom.h(Loose, {"name": "Alice"}), root_element)
    err = capsys.readouterr().err
    assert "destructured" in err.lower() or "unwrapped" in err.lower()


def test_untrack_silences_destructured_warning(wyb, root_element, capsys):
    """Wrapping the read in ``untrack`` is the canonical opt-out."""
    vdom, comp_mod, reactivity = wyb["vdom"], wyb["component"], wyb["reactivity"]
    from wybthon._warnings import _reset_warning_dedupe, set_dev_mode

    set_dev_mode(True)
    _reset_warning_dedupe()

    @comp_mod.component
    def Counter(initial=0):
        seed = reactivity.untrack(initial)
        count, _set_count = reactivity.create_signal(seed)
        return vdom.h("p", {}, count)

    vdom.render(vdom.h(Counter, {"initial": 7}), root_element)
    err = capsys.readouterr().err
    assert "destructured" not in err.lower() and "unwrapped" not in err.lower()


def test_effect_silences_destructured_warning(wyb, root_element, capsys):
    """Reading a prop inside ``create_effect`` subscribes correctly -- no warning."""
    vdom, comp_mod, reactivity = wyb["vdom"], wyb["component"], wyb["reactivity"]
    from wybthon._warnings import _reset_warning_dedupe, set_dev_mode

    set_dev_mode(True)
    _reset_warning_dedupe()

    @comp_mod.component
    def Logger(name="x"):
        log = []
        reactivity.create_effect(lambda: log.append(name()))
        return vdom.h("p", {}, "x")

    vdom.render(vdom.h(Logger, {"name": "Alice"}), root_element)
    err = capsys.readouterr().err
    assert "destructured" not in err.lower() and "unwrapped" not in err.lower()


def test_reactive_props_get_default_is_not_sticky():
    """``ReactiveProps.get(key, default)`` returns the *current* default for missing keys."""
    from wybthon.reactivity import ReactiveProps

    p = ReactiveProps({}, {})
    g1 = p.get("missing", "first")
    g2 = p.get("missing", "second")

    assert g1() == "first"
    assert g2() == "second"
    # No sticky signal should have been allocated.
    assert "missing" not in object.__getattribute__(p, "_signals")


def test_memo_silences_destructured_warning(wyb, root_element, capsys):
    """Reading a prop inside ``create_memo`` subscribes correctly -- no warning."""
    vdom, comp_mod, reactivity = wyb["vdom"], wyb["component"], wyb["reactivity"]
    from wybthon._warnings import _reset_warning_dedupe, set_dev_mode

    set_dev_mode(True)
    _reset_warning_dedupe()

    @comp_mod.component
    def Greeter(name="x"):
        full = reactivity.create_memo(lambda: f"hi, {name()}!")
        return vdom.h("p", {}, full)

    vdom.render(vdom.h(Greeter, {"name": "Alice"}), root_element)
    err = capsys.readouterr().err
    assert "destructured" not in err.lower() and "unwrapped" not in err.lower()


def test_for_warns_on_plain_list(wyb, root_element, capsys):
    """``For`` warns when ``each=`` is a static list."""
    vdom = wyb["vdom"]
    from wybthon._warnings import _reset_warning_dedupe, set_dev_mode
    from wybthon.flow import For

    set_dev_mode(True)
    _reset_warning_dedupe()

    vdom.render(
        vdom.h(For, {"each": ["a", "b"]}, lambda item, _idx: vdom.h("span", {}, item)),
        root_element,
    )
    err = capsys.readouterr().err
    assert "plain list" in err.lower()


def test_for_does_not_warn_with_signal(wyb, root_element, capsys):
    """``For`` is silent when given a signal accessor."""
    vdom, reactivity = wyb["vdom"], wyb["reactivity"]
    from wybthon._warnings import _reset_warning_dedupe, set_dev_mode
    from wybthon.flow import For

    set_dev_mode(True)
    _reset_warning_dedupe()

    items, _set_items = reactivity.create_signal(["a", "b"])
    vdom.render(
        vdom.h(For, {"each": items}, lambda item, _idx: vdom.h("span", {}, item)),
        root_element,
    )
    err = capsys.readouterr().err
    assert "plain list" not in err.lower()


# ---------------------------------------------------------------------------
# Naming cleanup
# ---------------------------------------------------------------------------


def test_dynamic_is_public():
    """``dynamic`` is exported from the top-level package."""
    import wybthon

    assert hasattr(wybthon, "dynamic")
    assert callable(wybthon.dynamic)


def test_class_underscore_is_canonical(wyb, root_element):
    """``class_=`` is the single canonical spelling and maps to ``class``."""
    vdom = wyb["vdom"]
    from wybthon.html import div

    vdom.render(div("a", class_="primary"), root_element)
    el = root_element.element.childNodes[0]
    assert el.attributes.get("class") == "primary"


def test_link_forwards_class_underscore(wyb, root_element):
    """``Link`` should treat ``class_=`` like an HTML helper (canonical class)."""
    vdom = wyb["vdom"]
    from wybthon.router import Link

    vdom.render(vdom.h(Link, {"to": "/foo", "class_": "btn"}, "X"), root_element)
    a = root_element.element.childNodes[0]
    assert a.tag == "a"
    assert "btn" in (a.attributes.get("class") or "")
