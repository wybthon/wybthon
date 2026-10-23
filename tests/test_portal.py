from conftest import StubNode, collect_texts

from wybthon import html
from wybthon.component import component
from wybthon.context import create_context, use_context
from wybthon.flow import Show
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
    view = html(t"<div><span>before</span>{Portal(html(t'<p>modal</p>'), mount=target_el)}</div>")
    root = wyb["reconciler"].render(view, root_element)
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
    root = wyb["reconciler"].render(
        html(t"<div>{Portal(html(t'<p>{msg()}</p>'), mount=target_el)}</div>"), root_element
    )
    assert texts(target) == ["hi"]
    set_msg("yo")
    flush()
    assert texts(target) == ["yo"]
    root.dispose()


def test_portal_unmount_via_show_removes_children_from_target(wyb, root_element):
    target, target_el = make_target(wyb)
    show, set_show = create_signal(True)
    view = html(t"<div>{Show(show, lambda: Portal(html(t'<p>modal</p>'), mount=target_el))}</div>")
    root = wyb["reconciler"].render(view, root_element)
    assert texts(target) == ["modal"]
    set_show(False)
    flush()
    assert texts(target) == []
    assert elements(target) == []
    set_show(True)
    flush()
    assert texts(target) == ["modal"]
    root.dispose()


def test_portal_inside_show_with_a_condition_expression(wyb, root_element):
    # `Show(open() and ..., Portal(...))`: the condition is a getter; the
    # portal (a prepared component call) mounts and unmounts with it.
    target, target_el = make_target(wyb)
    open_, set_open = create_signal(0)
    view = html(t"<div>{Show(open_() > 0, Portal(html(t'<p>modal {open_()}</p>'), mount=target_el))}</div>")
    root = wyb["reconciler"].render(view, root_element)
    assert texts(target) == []
    set_open(1)
    flush()
    assert texts(target) == ["modal ", "1"]
    set_open(2)
    flush()
    assert texts(target) == ["modal ", "2"]
    set_open(0)
    flush()
    assert texts(target) == []
    root.dispose()


def test_portal_target_outside_render_root_receives_delegated_events(wyb, root_element):
    target, target_el = make_target(wyb)
    clicks: list[str] = []

    def go(e):
        clicks.append("portal")

    root = wyb["reconciler"].render(
        html(t"<div>{Portal(html(t'<button onclick={go}>go</button>'), mount=target_el)}</div>"), root_element
    )
    backend = wyb["kernel"]._backend
    assert target in backend.roots()
    backend.dispatch("click", elements(target)[0])
    assert clicks == ["portal"]
    root.dispose()
    assert target not in backend.roots()


def test_portal_into_the_render_root_keeps_delegation_after_unmount(wyb, root_element):
    show, set_show = create_signal(True)
    clicks: list[str] = []

    def app(e):
        clicks.append("app")

    view = html(t"""<div>
        <button onclick={app}>app</button>
        {Show(show, lambda: Portal(html(t"<p>modal</p>"), mount=root_element))}
    </div>""")
    wyb["reconciler"].render(view, root_element)
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
    view = html(t"<div>{Portal([html(t'<p>a</p>'), html(t'<p>b</p>')], mount=target_el)}</div>")
    root = wyb["reconciler"].render(view, root_element)
    assert texts(target) == ["a", "b"]
    root.dispose()
    assert elements(target) == []
    assert texts(target) == []


def test_portal_mount_by_node_id_and_callable_children(wyb, root_element):
    # `mount=target_el.node_id` is dynamic: the portal reads the getter once.
    target, target_el = make_target(wyb)
    count, set_count = create_signal(0)
    view = html(t"<div>{Portal(lambda: html(t'<p>{f"count={count()}"}</p>'), mount=target_el.node_id)}</div>")
    root = wyb["reconciler"].render(view, root_element)
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
        return html(t"<p>{use_context(Theme)}</p>")

    root = wyb["reconciler"].render(Theme("dark", html(t"<div>{Portal(Child(), mount=target_el)}</div>")), root_element)
    assert texts(target) == ["dark"]
    root.dispose()
