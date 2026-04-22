"""Tests for *reactive holes* — fine-grained reactive expressions in VNode trees.

Reactive holes are zero-arg callables that appear as children or prop values
inside a ``VNode``.  The reconciler treats each hole as an independent
reactive scope: its getter is wrapped in an effect, and only the hole
re-runs when its dependencies change.  The surrounding component body
runs **once**.

This is the SolidJS-style fine-grained reactivity model, adapted to a
batched VDOM for Pyodide's bridge-overhead constraints.
"""

import time

from conftest import collect_texts

# --------------------------------------------------------------------------- #
# Reactive hole basics
# --------------------------------------------------------------------------- #


def test_signal_getter_as_child_creates_hole(wyb, root_element):
    """Passing a signal getter as a child auto-wraps it as a reactive hole."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]

    sig = reactivity.signal("hello")

    def App(props):
        return vdom.h("p", {}, sig.get)

    vdom.render(vdom.h(App, {}), root_element)
    assert "hello" in collect_texts(root_element.element)

    sig.set("world")
    time.sleep(0.05)
    assert "world" in collect_texts(root_element.element)


def test_explicit_dynamic_helper(wyb, root_element):
    """``dynamic(getter)`` explicitly wraps a getter as a reactive hole."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]

    sig = reactivity.signal(0)

    def App(props):
        return vdom.h("p", {}, vdom.dynamic(lambda: f"value={sig.get()}"))

    vdom.render(vdom.h(App, {}), root_element)
    assert "value=0" in collect_texts(root_element.element)

    sig.set(42)
    time.sleep(0.05)
    assert "value=42" in collect_texts(root_element.element)


def test_component_body_runs_once(wyb, root_element):
    """The component body must run exactly once during mount."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]

    sig = reactivity.signal(0)
    body_runs = [0]

    def Counter(props):
        body_runs[0] += 1
        return vdom.h("p", {}, sig.get)

    vdom.render(vdom.h(Counter, {}), root_element)
    assert body_runs[0] == 1

    for v in (1, 2, 3, 4, 5):
        sig.set(v)
        time.sleep(0.02)

    assert body_runs[0] == 1, "body still runs only once after multiple updates"
    assert "5" in collect_texts(root_element.element)


def test_hole_runs_independently(wyb, root_element):
    """Each hole has its own effect — only the changed hole re-runs."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]

    a = reactivity.signal("A0")
    b = reactivity.signal("B0")
    a_runs = [0]
    b_runs = [0]

    def get_a():
        a_runs[0] += 1
        return a.get()

    def get_b():
        b_runs[0] += 1
        return b.get()

    def App(props):
        return vdom.h(
            "div",
            {},
            vdom.h("span", {}, get_a),
            vdom.h("span", {}, get_b),
        )

    vdom.render(vdom.h(App, {}), root_element)
    assert a_runs[0] == 1
    assert b_runs[0] == 1

    a.set("A1")
    time.sleep(0.05)
    assert a_runs[0] == 2
    assert b_runs[0] == 1, "b's hole did not re-run"

    b.set("B1")
    time.sleep(0.05)
    assert a_runs[0] == 2, "a's hole did not re-run"
    assert b_runs[0] == 2


def test_hole_with_memo(wyb, root_element):
    """A memo can be used as a reactive hole getter."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]

    sig = reactivity.signal(2)
    compute_runs = [0]

    def expensive():
        compute_runs[0] += 1
        return sig.get() * 10

    doubled = reactivity.create_memo(expensive)

    def App(props):
        return vdom.h("p", {}, doubled)

    vdom.render(vdom.h(App, {}), root_element)
    assert "20" in collect_texts(root_element.element)
    assert compute_runs[0] == 1

    sig.set(3)
    time.sleep(0.05)
    assert "30" in collect_texts(root_element.element)
    assert compute_runs[0] == 2


# --------------------------------------------------------------------------- #
# Reactive holes for props
# --------------------------------------------------------------------------- #


def test_reactive_class_prop(wyb, root_element):
    """A callable ``class`` prop becomes a reactive hole for the attribute."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]

    cls = reactivity.signal("foo")

    def App(props):
        return vdom.h("p", {"class": cls.get}, "hi")

    vdom.render(vdom.h(App, {}), root_element)
    el = root_element.element.childNodes[0]
    assert el.attributes.get("class") == "foo"

    cls.set("bar baz")
    time.sleep(0.05)
    assert el.attributes.get("class") == "bar baz"


def test_reactive_style_prop(wyb, root_element):
    """A callable ``style`` prop reactively updates style properties."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]

    color = reactivity.signal("red")

    def App(props):
        return vdom.h("p", {"style": lambda: {"color": color.get()}}, "hi")

    vdom.render(vdom.h(App, {}), root_element)
    el = root_element.element.childNodes[0]
    assert el.style._props.get("color") == "red"

    color.set("blue")
    time.sleep(0.05)
    assert el.style._props.get("color") == "blue"


def test_reactive_dataset_prop(wyb, root_element):
    """A callable ``dataset`` prop updates ``data-*`` attributes reactively."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]

    state = reactivity.signal({"role": "button", "id": "1"})

    def App(props):
        return vdom.h("p", {"dataset": state.get}, "hi")

    vdom.render(vdom.h(App, {}), root_element)
    el = root_element.element.childNodes[0]
    assert el.attributes.get("data-role") == "button"
    assert el.attributes.get("data-id") == "1"

    state.set({"role": "link", "id": "2"})
    time.sleep(0.05)
    assert el.attributes.get("data-role") == "link"
    assert el.attributes.get("data-id") == "2"


def test_reactive_value_prop(wyb, root_element):
    """A callable ``value`` prop sets the DOM property reactively."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]

    val = reactivity.signal("a")

    def App(props):
        return vdom.h("input", {"value": val.get})

    vdom.render(vdom.h(App, {}), root_element)
    el = root_element.element.childNodes[0]
    assert el.value == "a"

    val.set("b")
    time.sleep(0.05)
    assert el.value == "b"


def test_reactive_attr_prop(wyb, root_element):
    """A callable plain attribute is reactively applied."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]

    title = reactivity.signal("first")

    def App(props):
        return vdom.h("p", {"title": title.get}, "hi")

    vdom.render(vdom.h(App, {}), root_element)
    el = root_element.element.childNodes[0]
    assert el.attributes.get("title") == "first"

    title.set("second")
    time.sleep(0.05)
    assert el.attributes.get("title") == "second"


def test_event_handlers_are_not_holes(wyb, root_element):
    """``on_*`` props must NOT be treated as reactive getters."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]

    handler_calls = [0]

    def my_handler(event):
        handler_calls[0] += 1

    body_runs = [0]

    def App(props):
        body_runs[0] += 1
        return vdom.h("button", {"on_click": my_handler}, "click me")

    vdom.render(vdom.h(App, {}), root_element)
    assert body_runs[0] == 1

    sig = reactivity.signal(0)

    def App2(props):
        return vdom.h(
            "button",
            {"on_click": my_handler, "title": lambda: f"clicked {sig.get()}"},
            "x",
        )

    vdom.render(vdom.h(App2, {}), wyb["dom"].Element(node=type(root_element.element)(tag="div")))


# --------------------------------------------------------------------------- #
# Mixed static + reactive children
# --------------------------------------------------------------------------- #


def test_mixed_static_and_reactive_children(wyb, root_element):
    """A node with both static text and a reactive hole interleaves correctly."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]

    name = reactivity.signal("Alice")

    def App(props):
        return vdom.h("p", {}, "Hello, ", name.get, "!")

    vdom.render(vdom.h(App, {}), root_element)
    texts = "".join(collect_texts(root_element.element))
    assert "Hello, Alice!" in texts

    name.set("Bob")
    time.sleep(0.05)
    texts = "".join(collect_texts(root_element.element))
    assert "Hello, Bob!" in texts


def test_hole_returning_vnode(wyb, root_element):
    """A reactive hole can return a ``VNode`` instead of text."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]

    show_emphasis = reactivity.signal(False)

    def render_text():
        if show_emphasis.get():
            return vdom.h("strong", {}, "important")
        return vdom.h("span", {}, "normal")

    def App(props):
        return vdom.h("p", {}, render_text)

    vdom.render(vdom.h(App, {}), root_element)
    el = root_element.element.childNodes[0]
    assert el.childNodes[0].tag == "span"

    show_emphasis.set(True)
    time.sleep(0.05)
    assert el.childNodes[0].tag == "strong"

    show_emphasis.set(False)
    time.sleep(0.05)
    assert el.childNodes[0].tag == "span"


def test_hole_returning_fragment(wyb, root_element):
    """A reactive hole can return a Fragment (multiple roots)."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]

    count = reactivity.signal(2)

    def render_items():
        n = count.get()
        return vdom.Fragment(*[vdom.h("li", {}, f"item {i}") for i in range(n)])

    def App(props):
        return vdom.h("ul", {}, render_items)

    vdom.render(vdom.h(App, {}), root_element)
    ul = root_element.element.childNodes[0]
    li_count = sum(1 for c in ul.childNodes if c.tag == "li")
    assert li_count == 2

    count.set(5)
    time.sleep(0.05)
    li_count = sum(1 for c in ul.childNodes if c.tag == "li")
    assert li_count == 5


def test_hole_returning_none_renders_nothing(wyb, root_element):
    """A hole returning ``None`` renders nothing visible."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]

    visible = reactivity.signal(False)

    def render_msg():
        if visible.get():
            return vdom.h("span", {}, "I'm here")
        return None

    def App(props):
        return vdom.h("div", {}, render_msg)

    vdom.render(vdom.h(App, {}), root_element)
    div = root_element.element.childNodes[0]
    text_content = "".join(collect_texts(div))
    assert "I'm here" not in text_content

    visible.set(True)
    time.sleep(0.05)
    text_content = "".join(collect_texts(div))
    assert "I'm here" in text_content

    visible.set(False)
    time.sleep(0.05)
    text_content = "".join(collect_texts(div))
    assert "I'm here" not in text_content


# --------------------------------------------------------------------------- #
# Reactive holes inside flow controls
# --------------------------------------------------------------------------- #


def test_show_works_with_holes(wyb, root_element):
    """``Show`` continues to work; its children may use reactive holes."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]
    flow = wyb["flow"]

    visible = reactivity.signal(True)
    name = reactivity.signal("alice")

    def App(props):
        return flow.Show(
            when=visible.get,
            children=lambda: vdom.h("p", {}, "name: ", name.get),
            fallback=lambda: vdom.h("p", {}, "(hidden)"),
        )

    vdom.render(vdom.h(App, {}), root_element)
    texts = "".join(collect_texts(root_element.element))
    assert "name: alice" in texts

    name.set("bob")
    time.sleep(0.05)
    texts = "".join(collect_texts(root_element.element))
    assert "name: bob" in texts

    visible.set(False)
    time.sleep(0.05)
    texts = "".join(collect_texts(root_element.element))
    assert "(hidden)" in texts
    assert "name:" not in texts


def test_for_works_with_holes(wyb, root_element):
    """``For`` mapping callbacks may use reactive holes."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]
    flow = wyb["flow"]

    items_sig = reactivity.signal(["a", "b", "c"])
    suffix = reactivity.signal("!")

    def App(props):
        return vdom.h(
            "ul",
            {},
            flow.For(
                each=items_sig.get,
                children=lambda item, idx: vdom.h(
                    "li",
                    {},
                    item,
                    lambda: suffix.get(),
                ),
            ),
        )

    vdom.render(vdom.h(App, {}), root_element)
    texts = "".join(collect_texts(root_element.element))
    assert "a!" in texts
    assert "b!" in texts
    assert "c!" in texts

    suffix.set("?")
    time.sleep(0.05)
    texts = "".join(collect_texts(root_element.element))
    assert "a?" in texts
    assert "b?" in texts
    assert "c?" in texts


# --------------------------------------------------------------------------- #
# Lifecycle: holes get cleaned up on unmount
# --------------------------------------------------------------------------- #


def test_hole_effect_disposed_on_unmount(wyb, root_element):
    """A reactive hole's effect is disposed when its parent unmounts."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]

    sig = reactivity.signal(0)
    runs = [0]

    def get_value():
        runs[0] += 1
        return sig.get()

    def App(props):
        return vdom.h("p", {}, get_value)

    tree = vdom.h(App, {})
    vdom.render(tree, root_element)
    assert runs[0] == 1

    sig.set(1)
    time.sleep(0.05)
    assert runs[0] == 2

    vdom._unmount(tree)
    sig.set(2)
    time.sleep(0.05)
    assert runs[0] == 2, "hole effect must be disposed after unmount"


def test_hole_inside_show_fallback_disposed(wyb, root_element):
    """When ``Show`` flips branches, the inactive branch's holes are disposed."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]
    flow = wyb["flow"]

    cond = reactivity.signal(True)
    branch_sig = reactivity.signal(0)
    branch_runs = [0]

    def get_branch_val():
        branch_runs[0] += 1
        return branch_sig.get()

    def App(props):
        return flow.Show(
            when=cond.get,
            children=lambda: vdom.h("p", {}, get_branch_val),
            fallback=lambda: vdom.h("p", {}, "no"),
        )

    vdom.render(vdom.h(App, {}), root_element)
    assert branch_runs[0] == 1

    branch_sig.set(1)
    time.sleep(0.05)
    assert branch_runs[0] == 2

    cond.set(False)
    time.sleep(0.05)
    runs_after_flip = branch_runs[0]

    branch_sig.set(99)
    time.sleep(0.05)
    assert branch_runs[0] == runs_after_flip, "inactive branch's hole must be disposed and not re-run"


# --------------------------------------------------------------------------- #
# Owner / scope semantics
# --------------------------------------------------------------------------- #


def test_on_cleanup_inside_hole_runs_on_dependency_change(wyb, root_element):
    """An ``on_cleanup`` registered inside a hole runs before the hole re-runs."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]

    sig = reactivity.signal(0)
    log = []

    def get_value():
        v = sig.get()
        log.append(f"run:{v}")
        reactivity.on_cleanup(lambda: log.append(f"cleanup:{v}"))
        return str(v)

    def App(props):
        return vdom.h("p", {}, get_value)

    tree = vdom.h(App, {})
    vdom.render(tree, root_element)
    assert log == ["run:0"]

    sig.set(1)
    time.sleep(0.05)
    assert "cleanup:0" in log
    assert "run:1" in log

    vdom._unmount(tree)
    assert "cleanup:1" in log


# --------------------------------------------------------------------------- #
# ReactiveProps on components + holes inside child components
# --------------------------------------------------------------------------- #


def test_reactive_props_via_getter(wyb, root_element):
    """Parent passes a getter as a prop; child invokes it inside a hole.

    This is the SolidJS pattern for cross-component reactivity: pass the
    accessor itself, not the value.  Inside the child, calling the getter
    inside a reactive hole creates a dependency on the parent's signal.
    """
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]

    parent_count = reactivity.signal(0)
    child_runs = [0]

    def Greeting(props):
        child_runs[0] += 1
        get_count = props["count"]
        return vdom.h("span", {}, lambda: f"count={get_count()}")

    def Parent(props):
        return vdom.h("div", {}, vdom.h(Greeting, {"count": parent_count.get}))

    vdom.render(vdom.h(Parent, {}), root_element)
    assert child_runs[0] == 1
    assert "count=0" in "".join(collect_texts(root_element.element))

    parent_count.set(7)
    time.sleep(0.05)
    assert child_runs[0] == 1, "child body must run only once"
    assert "count=7" in "".join(collect_texts(root_element.element))


# --------------------------------------------------------------------------- #
# Untrack still works inside holes
# --------------------------------------------------------------------------- #


def test_untrack_inside_hole(wyb, root_element):
    """``untrack`` inside a hole prevents that read from being a dependency."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]

    a = reactivity.signal(0)
    b = reactivity.signal(0)
    runs = [0]

    def get_value():
        runs[0] += 1
        with_a = a.get()
        with_b = reactivity.untrack(b.get)
        return f"{with_a}:{with_b}"

    def App(props):
        return vdom.h("p", {}, get_value)

    vdom.render(vdom.h(App, {}), root_element)
    assert runs[0] == 1
    assert "0:0" in "".join(collect_texts(root_element.element))

    b.set(99)
    time.sleep(0.05)
    assert runs[0] == 1, "untracked b must not trigger re-run"

    a.set(1)
    time.sleep(0.05)
    assert runs[0] == 2
    assert "1:99" in "".join(collect_texts(root_element.element))


# --------------------------------------------------------------------------- #
# Multiple holes on one element
# --------------------------------------------------------------------------- #


def test_multiple_holes_on_same_element(wyb, root_element):
    """An element can have multiple reactive holes (props + children)."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]

    title = reactivity.signal("t1")
    body = reactivity.signal("b1")

    def App(props):
        return vdom.h("p", {"title": title.get}, body.get)

    vdom.render(vdom.h(App, {}), root_element)
    el = root_element.element.childNodes[0]
    assert el.attributes.get("title") == "t1"
    assert "b1" in collect_texts(el)

    title.set("t2")
    time.sleep(0.05)
    assert el.attributes.get("title") == "t2"
    assert "b1" in collect_texts(el)

    body.set("b2")
    time.sleep(0.05)
    assert el.attributes.get("title") == "t2"
    assert "b2" in collect_texts(el)


# --------------------------------------------------------------------------- #
# Children prop changes propagate through pass-through components
# --------------------------------------------------------------------------- #


def test_provider_swaps_child_component_via_parent_hole(wyb, root_element):
    """Router-style scenario: a parent hole swaps the Provider's child component.

    A parent reactive hole produces ``h(Provider, {...}, h(NewComp, ...))``
    where the child *component* differs across renders (not just its
    props).  The Provider must propagate the new children into its
    subtree so the new component actually mounts.  This is the regression
    that broke ``wyb dev`` route navigation when components became run-once.
    """
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]
    context_mod = wyb["context"]

    Theme = context_mod.create_context("light")

    def HomePage(props):
        return vdom.h("section", {"data-page": "home"}, "home-page")

    def AboutPage(props):
        return vdom.h("section", {"data-page": "about"}, "about-page")

    pages = {"home": HomePage, "about": AboutPage}
    current = reactivity.signal("home")

    def Outer(props):
        return lambda: vdom.h(
            context_mod.Provider,
            {"context": Theme, "value": "dark"},
            vdom.h(pages[current.get()], {}),
        )

    vdom.render(vdom.h(Outer, {}), root_element)
    texts = collect_texts(root_element.element)
    assert "home-page" in texts
    assert "about-page" not in texts

    current.set("about")
    time.sleep(0.05)
    texts = collect_texts(root_element.element)
    assert "about-page" in texts, f"expected new component to mount after children change, got: {texts}"
    assert "home-page" not in texts, "old component must be unmounted when children change"

    current.set("home")
    time.sleep(0.05)
    texts = collect_texts(root_element.element)
    assert "home-page" in texts
    assert "about-page" not in texts


def test_provider_keeps_context_after_children_change(wyb, root_element):
    """A Provider keeps providing its context value across children changes."""
    vdom = wyb["vdom"]
    reactivity = wyb["reactivity"]
    context_mod = wyb["context"]

    Theme = context_mod.create_context("light")

    def HomeReader(props):
        theme = context_mod.use_context(Theme)
        return vdom.h("p", {}, f"home:{theme}")

    def AboutReader(props):
        theme = context_mod.use_context(Theme)
        return vdom.h("p", {}, f"about:{theme}")

    pages = {"home": HomeReader, "about": AboutReader}
    current = reactivity.signal("home")

    def App(props):
        return lambda: vdom.h(
            context_mod.Provider,
            {"context": Theme, "value": "dark"},
            vdom.h(pages[current.get()], {}),
        )

    vdom.render(vdom.h(App, {}), root_element)
    assert "home:dark" in "".join(collect_texts(root_element.element))

    current.set("about")
    time.sleep(0.05)
    assert "about:dark" in "".join(collect_texts(root_element.element))
