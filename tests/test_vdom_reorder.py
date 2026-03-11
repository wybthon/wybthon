import importlib
import time

from conftest import StubNode, texts_of_children

# Import wybthon BEFORE stubs so __init__.py runs with _IN_BROWSER=False
import wybthon  # noqa: F401


def test_keyed_reorder_reverse(browser_stubs):
    dom_mod = importlib.import_module("wybthon.dom")
    importlib.reload(dom_mod)
    vdom_mod = importlib.import_module("wybthon.vdom")
    importlib.reload(vdom_mod)

    root = dom_mod.Element(node=StubNode(tag="div"))

    def make_view(order):
        return vdom_mod.h(
            "ul",
            {},
            *[vdom_mod.h("li", {"key": k}, k) for k in order],
        )

    initial = ["A", "B", "C", "D"]
    view1 = make_view(initial)
    vdom_mod.render(view1, root)
    ul = root.element.childNodes[0]
    assert texts_of_children(ul) == initial

    # Capture identity of nodes by their text content
    initial_nodes = {t: ul.childNodes[i] for i, t in enumerate(initial)}

    # Reverse order
    reversed_order = list(reversed(initial))
    view2 = make_view(reversed_order)
    vdom_mod.render(view2, root)
    ul2 = root.element.childNodes[0]
    assert texts_of_children(ul2) == reversed_order

    # Verify node identity reused for each key
    for t in reversed_order:
        assert ul2.childNodes[reversed_order.index(t)] is initial_nodes[t]


def test_keyed_reorder_move_middle_to_front_and_insert_remove(browser_stubs):
    dom_mod = importlib.import_module("wybthon.dom")
    importlib.reload(dom_mod)
    vdom_mod = importlib.import_module("wybthon.vdom")
    importlib.reload(vdom_mod)

    root = dom_mod.Element(node=StubNode(tag="div"))

    def make_view(order):
        return vdom_mod.h(
            "ul",
            {},
            *[vdom_mod.h("li", {"key": k}, k) for k in order],
        )

    initial = ["A", "B", "C", "D", "E"]
    vdom_mod.render(make_view(initial), root)
    ul = root.element.childNodes[0]
    assert texts_of_children(ul) == initial
    initial_nodes = {t: ul.childNodes[i] for i, t in enumerate(initial)}

    # New order: move C to front, drop B, add F at end, swap D/E
    target = ["C", "A", "E", "D", "F"]
    vdom_mod.render(make_view(target), root)
    ul2 = root.element.childNodes[0]
    assert texts_of_children(ul2) == target

    # Identity preserved for existing keys A,C,D,E
    for t in ["A", "C", "D", "E"]:
        idx = target.index(t)
        assert ul2.childNodes[idx] is initial_nodes[t]

    # F is new
    assert target[-1] == "F"
    assert ul2.childNodes[-1] is not initial_nodes.get("F")


def test_keyed_reorder_micro_time_smoke(browser_stubs):
    # A tiny smoke micro-benchmark asserting it runs fast enough in our stubbed env
    dom_mod = importlib.import_module("wybthon.dom")
    importlib.reload(dom_mod)
    vdom_mod = importlib.import_module("wybthon.vdom")
    importlib.reload(vdom_mod)

    root = dom_mod.Element(node=StubNode(tag="div"))
    N = 200
    keys = [f"k{i}" for i in range(N)]

    def make_view(order):
        return vdom_mod.h("ul", {}, *[vdom_mod.h("li", {"key": k}, k) for k in order])

    vdom_mod.render(make_view(keys), root)
    start = time.time()
    vdom_mod.render(make_view(list(reversed(keys))), root)
    elapsed = time.time() - start
    # This threshold is generous and only meant to catch pathological regressions
    assert elapsed < 0.3
