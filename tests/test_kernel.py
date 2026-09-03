def test_create_element_op(wyb):
    """CREATE_ELEMENT produces the expected stub-DOM state."""
    kernel = wyb["kernel"]
    node_id = kernel.alloc_id()

    kernel.emit((kernel.OP_CREATE_ELEMENT, node_id, "div"))

    # get_node() automatically calls commit()
    node = kernel.get_node(node_id)
    assert node is not None
    assert node.tag == "div"


def test_set_attr_removes_with_none(wyb):
    """SET_ATTR with None removes the attribute."""
    kernel = wyb["kernel"]
    node_id = kernel.alloc_id()

    kernel.emit((kernel.OP_CREATE_ELEMENT, node_id, "div"))
    kernel.emit((kernel.OP_SET_ATTR, node_id, "id", "my-div"))

    node = kernel.get_node(node_id)
    assert node.getAttribute("id") == "my-div"

    # Remove the attribute
    kernel.emit((kernel.OP_SET_ATTR, node_id, "id", None))
    node = kernel.get_node(node_id)
    assert node.getAttribute("id") is None


def test_insert_with_none_anchor_appends(wyb):
    """INSERT with a None anchor appends to the parent."""
    kernel = wyb["kernel"]
    parent_id = kernel.alloc_id()
    child_id = kernel.alloc_id()

    kernel.emit((kernel.OP_CREATE_ELEMENT, parent_id, "div"))
    kernel.emit((kernel.OP_CREATE_ELEMENT, child_id, "span"))
    kernel.emit((kernel.OP_INSERT, parent_id, child_id, None))

    parent = kernel.get_node(parent_id)
    child = kernel.get_node(child_id)
    assert child in parent.childNodes


def test_remove_op(wyb):
    """REMOVE deletes the node from its parent."""
    kernel = wyb["kernel"]
    parent_id = kernel.alloc_id()
    child_id = kernel.alloc_id()

    kernel.emit((kernel.OP_CREATE_ELEMENT, parent_id, "div"))
    kernel.emit((kernel.OP_CREATE_ELEMENT, child_id, "span"))
    kernel.emit((kernel.OP_INSERT, parent_id, child_id, None))

    kernel.emit((kernel.OP_REMOVE, child_id))
    parent = kernel.get_node(parent_id)
    child = kernel.get_node(child_id)
    assert child not in parent.childNodes


def test_create_and_set_text(wyb):
    """CREATE_TEXT and SET_TEXT modify a text node's value."""
    kernel = wyb["kernel"]
    text_id = kernel.alloc_id()

    kernel.emit((kernel.OP_CREATE_TEXT, text_id, "hello"))
    node = kernel.get_node(text_id)
    assert node.nodeValue == "hello"

    kernel.emit((kernel.OP_SET_TEXT, text_id, "world"))
    node = kernel.get_node(text_id)
    assert node.nodeValue == "world"


def test_set_prop(wyb):
    """SET_PROP applies a DOM property assignment."""
    kernel = wyb["kernel"]
    input_id = kernel.alloc_id()

    kernel.emit((kernel.OP_CREATE_ELEMENT, input_id, "input"))
    kernel.emit((kernel.OP_SET_PROP, input_id, "value", "test-val"))

    node = kernel.get_node(input_id)
    assert node.value == "test-val"


def test_set_style(wyb):
    """SET_STYLE applies a style property, and None removes it."""
    kernel = wyb["kernel"]
    div_id = kernel.alloc_id()

    kernel.emit((kernel.OP_CREATE_ELEMENT, div_id, "div"))
    kernel.emit((kernel.OP_SET_STYLE, div_id, {"color": "red", "margin": "10px"}))

    node = kernel.get_node(div_id)
    assert node.style._props.get("color") == "red"

    # Remove color
    kernel.emit((kernel.OP_SET_STYLE, div_id, {"color": None}))
    node = kernel.get_node(div_id)
    assert "color" not in node.style._props
    assert node.style._props.get("margin") == "10px"


def test_insert_with_anchor(wyb):
    """INSERT with a real anchor places the child before the anchor."""
    kernel = wyb["kernel"]
    parent_id = kernel.alloc_id()
    child1_id = kernel.alloc_id()
    child2_id = kernel.alloc_id()

    kernel.emit((kernel.OP_CREATE_ELEMENT, parent_id, "div"))
    kernel.emit((kernel.OP_CREATE_ELEMENT, child1_id, "span"))
    kernel.emit((kernel.OP_CREATE_ELEMENT, child2_id, "b"))

    kernel.emit((kernel.OP_INSERT, parent_id, child1_id, None))
    # Insert child2 BEFORE child1
    kernel.emit((kernel.OP_INSERT, parent_id, child2_id, child1_id))

    parent = kernel.get_node(parent_id)
    child1 = kernel.get_node(child1_id)
    child2 = kernel.get_node(child2_id)

    # child2 should be first
    assert parent.childNodes == [child2, child1]


def test_register_and_clone_tpl(wyb):
    """REGISTER_TPL and CLONE_TPL assign dense id blocks in pre-order."""
    kernel = wyb["kernel"]
    html = "<div><span></span>hello</div>"

    # template_id() automatically emits OP_REGISTER_TPL if unseen
    tpl_id = kernel.template_id(html)

    # 3 nodes: div, span, text
    count = 3
    first_id = kernel.alloc_ids(count)

    kernel.emit((kernel.OP_CLONE_TPL, first_id, count, tpl_id))

    div = kernel.get_node(first_id)
    span = kernel.get_node(first_id + 1)
    txt = kernel.get_node(first_id + 2)

    assert div.tag == "div"
    assert span.tag == "span"
    assert txt.nodeValue == "hello"


def test_listen_unlisten_refcounting(wyb):
    """Root listener is installed/removed based on active listener counts."""
    kernel = wyb["kernel"]
    node1_id = kernel.alloc_id()
    node2_id = kernel.alloc_id()
    backend = kernel._backend

    kernel.emit((kernel.OP_CREATE_ELEMENT, node1_id, "button"))
    kernel.emit((kernel.OP_CREATE_ELEMENT, node2_id, "button"))

    # First listener installs root
    kernel.emit((kernel.OP_LISTEN, node1_id, "click"))
    kernel.commit()
    assert "click" in backend._root_listeners

    # Second listener doesn't break it
    kernel.emit((kernel.OP_LISTEN, node2_id, "click"))
    kernel.commit()

    # Unlisten first, root remains
    kernel.emit((kernel.OP_UNLISTEN, node1_id, "click"))
    kernel.commit()
    assert "click" in backend._root_listeners

    # Unlisten last, root removed
    kernel.emit((kernel.OP_UNLISTEN, node2_id, "click"))
    kernel.commit()
    assert "click" not in backend._root_listeners


def test_release_op(wyb):
    """RELEASE drops registry entries and listener sets."""
    kernel = wyb["kernel"]
    node_id = kernel.alloc_id()
    backend = kernel._backend

    kernel.emit((kernel.OP_CREATE_ELEMENT, node_id, "div"))
    kernel.emit((kernel.OP_LISTEN, node_id, "click"))
    kernel.commit()

    assert node_id in backend._nodes
    assert "click" in backend._root_listeners

    # Release node
    kernel.emit((kernel.OP_RELEASE, [node_id]))
    kernel.commit()

    assert node_id not in backend._nodes
    assert "click" not in backend._root_listeners


def test_reset_behavior(wyb):
    """reset() clears buffers and resets id allocation counters."""
    kernel = wyb["kernel"]
    backend = kernel._backend

    # Emit something to make the state dirty
    node_id = kernel.alloc_id()
    kernel.emit((kernel.OP_CREATE_ELEMENT, node_id, "div"))

    # Reset while passing the backend back in so it remains functional
    kernel.reset(backend=backend)

    # id allocation should start back at 1, buffer should be empty
    new_id = kernel.alloc_id()
    assert new_id == 1
    # Because _ops is a private module-level list alias, we check it via the kernel
    assert len(kernel._ops) == 0
