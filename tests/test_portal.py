from conftest import StubNode, collect_texts

from wybthon.component import component
from wybthon.context import create_context, use_context
from wybthon.flow import Show
from wybthon.html import div, p, span
from wybthon.portal import Portal
from wybthon.reactivity import create_signal, flush


def texts(node):
    return [t for t in collect_texts(node) if t]


def elements(node):
    return [n for n in node.childNodes if n.tag]


def make_target(wyb):
    node = StubNode(tag="div")
    return node, wyb["dom"].Element(node=node)


def test_portal_renders_children_into_mount_element(wyb, root_element):
    target, target_el = make_target(wyb)
    root = wyb["reconciler"].render(div(span("before"), Portal(p("modal"), mount=target_el)), root_element)
    assert texts(target) == ["modal"]
    assert elements(target)[0].tag == "p"
    # Only the sibling element stays in the original spot; the portal leaves no element behind.
    container_div = root_element.element.childNodes[0]
    assert [n.tag for n in elements(container_div)] == ["span"]
    assert texts(root_element.element) == ["before"]
    root.dispose()


def test_portal_children_update_reactively(wyb, root_element):
    target, target_el = make_target(wyb)
    msg, set_msg = create_signal("hi")
    root = wyb["reconciler"].render(div(Portal(p(msg), mount=target_el)), root_element)
    assert texts(target) == ["hi"]
    set_msg("yo")
    flush()
    assert texts(target) == ["yo"]
    root.dispose()


def test_portal_unmount_via_show_removes_children_from_target(wyb, root_element):
    target, target_el = make_target(wyb)
    show, set_show = create_signal(True)
    root = wyb["reconciler"].render(div(Show(show, lambda: Portal(p("modal"), mount=target_el))), root_element)
    assert texts(target) == ["modal"]
    set_show(False)
    flush()
    assert texts(target) == []
    assert elements(target) == []
    set_show(True)
    flush()
    assert texts(target) == ["modal"]
    root.dispose()


def test_portal_target_outside_render_root_receives_delegated_events(wyb, root_element):
    from wybthon.html import button

    target, target_el = make_target(wyb)
    clicks: list[str] = []
    root = wyb["reconciler"].render(
        div(Portal(button("go", on_click=lambda e: clicks.append("portal")), mount=target_el)), root_element
    )
    backend = wyb["kernel"]._backend
    assert target in backend.roots()
    backend.dispatch("click", elements(target)[0])
    assert clicks == ["portal"]
    root.dispose()
    assert target not in backend.roots()


def test_portal_into_the_render_root_keeps_delegation_after_unmount(wyb, root_element):
    from wybthon.html import button

    show, set_show = create_signal(True)
    clicks: list[str] = []
    wyb["reconciler"].render(
        div(
            button("app", on_click=lambda e: clicks.append("app")),
            Show(show, lambda: Portal(p("modal"), mount=root_element)),
        ),
        root_element,
    )
    backend = wyb["kernel"]._backend
    set_show(False)
    flush()
    # Unrooting the portal's target must not unroot the app root it shares.
    assert root_element.element in backend.roots()
    app_button = elements(root_element.element.childNodes[0])[0]
    backend.dispatch("click", app_button)
    assert clicks == ["app"]


def test_root_dispose_removes_portal_children(wyb, root_element):
    target, target_el = make_target(wyb)
    root = wyb["reconciler"].render(div(Portal([p("a"), p("b")], mount=target_el)), root_element)
    assert texts(target) == ["a", "b"]
    root.dispose()
    assert elements(target) == []
    assert texts(target) == []


def test_portal_mount_by_node_id_and_callable_children(wyb, root_element):
    target, target_el = make_target(wyb)
    count, set_count = create_signal(0)
    root = wyb["reconciler"].render(
        div(Portal(lambda: p(f"count={count()}"), mount=target_el.node_id)),
        root_element,
    )
    assert texts(target) == ["count=0"]
    set_count(3)
    flush()
    assert texts(target) == ["count=3"]
    root.dispose()
    assert texts(target) == []


def test_portal_children_keep_context_from_original_tree(wyb, root_element):
    target, target_el = make_target(wyb)
    Theme = create_context("none")

    @component
    def Child():
        return p(use_context(Theme))

    root = wyb["reconciler"].render(Theme("dark", div(Portal(Child(), mount=target_el))), root_element)
    assert texts(target) == ["dark"]
    root.dispose()
