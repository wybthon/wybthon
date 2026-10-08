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
    """REGISTER_TPL and CLONE assign dense id blocks in pre-order and fill text slots."""
    kernel = wyb["kernel"]
    parent_id = kernel.alloc_id()
    kernel.emit((kernel.OP_CREATE_ELEMENT, parent_id, "section"))

    class Shape:
        html = "<div><span></span> </div>"
        count = 3
        texts = [2]
        listens = [[1, "click"]]
        tpl = 0

    shape = Shape()
    tpl_id = kernel.register_template(shape)
    assert shape.tpl == tpl_id
    first_id = kernel.alloc_ids(3)
    kernel.emit((kernel.OP_CLONE, first_id, tpl_id, parent_id, None, "hello"))

    div = kernel.get_node(first_id)
    span = kernel.get_node(first_id + 1)
    txt = kernel.get_node(first_id + 2)

    assert div.tag == "div"
    assert div.parentNode is kernel.get_node(parent_id)
    assert span.tag == "span"
    assert txt.nodeValue == "hello"
    assert "click" in kernel._backend._listen[first_id + 1]

    kernel.emit((kernel.OP_DISPOSE, first_id))
    kernel.commit()
    assert kernel.get_node(first_id + 1) is None
    assert not kernel._backend._listen


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


class _Shape:
    """A minimal compiled shape for `register_template`."""

    def __init__(self, html, count, texts=(), listens=()):
        self.html = html
        self.count = count
        self.texts = list(texts)
        self.listens = [list(item) for item in listens]
        self.tpl = 0


def test_register_template_emits_one_registration(wyb):
    """REGISTER_TPL carries the skeleton, node count, text offsets, and delegated events."""
    kernel = wyb["kernel"]
    kernel.commit()
    shape = _Shape("<li><a> </a></li>", 3, texts=[2], listens=[(1, "click")])
    tpl_id = kernel.register_template(shape)
    assert kernel._ops[-1] == (kernel.OP_REGISTER_TPL, tpl_id, "<li><a> </a></li>", 3, [2], [[1, "click"]])
    second = kernel.register_template(_Shape("<p><b></b></p>", 2))
    assert second == tpl_id + 1
    assert not hasattr(kernel, "template_id")
    assert not hasattr(kernel, "OP_CLONE_TPL")
    assert not hasattr(kernel, "OP_REMOVE_RANGE")


def test_clone_inserts_before_anchor_and_fills_every_text_slot(wyb):
    kernel = wyb["kernel"]
    parent_id, anchor_id = kernel.alloc_id(), kernel.alloc_id()
    kernel.emit((kernel.OP_CREATE_ELEMENT, parent_id, "ul"))
    kernel.emit((kernel.OP_CREATE_COMMENT, anchor_id, "end"))
    kernel.emit((kernel.OP_INSERT, parent_id, anchor_id, None))
    shape = _Shape("<li> <b> </b></li>", 4, texts=[1, 3])
    tpl_id = kernel.register_template(shape)
    first = kernel.alloc_ids(4)
    second = kernel.alloc_ids(4)
    kernel.emit((kernel.OP_CLONE, first, tpl_id, parent_id, anchor_id, "one", "1"))
    kernel.emit((kernel.OP_CLONE, second, tpl_id, parent_id, anchor_id, "two", "2"))
    parent = kernel.get_node(parent_id)
    rows = [kernel.get_node(first), kernel.get_node(second)]
    assert parent.childNodes[:2] == rows
    assert parent.childNodes[2] is kernel.get_node(anchor_id)
    assert [kernel.get_node(first + 1).nodeValue, kernel.get_node(first + 3).nodeValue] == ["one", "1"]
    assert [kernel.get_node(second + 1).nodeValue, kernel.get_node(second + 3).nodeValue] == ["two", "2"]
    # Clones are independent copies of the prototype.
    assert kernel.get_node(first + 2) is not kernel.get_node(second + 2)


def test_dispose_range_removes_siblings_and_releases_descendants(wyb):
    """DISPOSE_RANGE removes a sibling range and releases every registered node inside it natively."""
    kernel = wyb["kernel"]
    backend = kernel._backend
    parent_id = kernel.alloc_id()
    kernel.emit((kernel.OP_CREATE_ELEMENT, parent_id, "div"))
    tpl_id = kernel.register_template(_Shape("<p><button> </button></p>", 3, texts=[2], listens=[(1, "click")]))
    rows = [kernel.alloc_ids(3) for _ in range(3)]
    for row in rows:
        kernel.emit((kernel.OP_CLONE, row, tpl_id, parent_id, None, f"row {row}"))
    kernel.commit()
    assert "click" in backend._root_listeners
    kernel.emit((kernel.OP_DISPOSE_RANGE, rows[0], rows[1]))
    kernel.commit()
    parent = kernel.get_node(parent_id)
    assert parent.childNodes == [kernel.get_node(rows[2])]
    for row in rows[:2]:
        assert all(kernel.get_node(row + offset) is None for offset in range(3))
    assert "click" in backend._root_listeners  # the last row still listens
    kernel.emit((kernel.OP_DISPOSE_RANGE, rows[2], rows[2]))
    kernel.commit()
    assert parent.childNodes == []
    assert not backend._listen
    assert "click" not in backend._root_listeners
    # Stale ids are ignored.
    kernel.emit((kernel.OP_DISPOSE_RANGE, rows[0], rows[2]))
    kernel.emit((kernel.OP_DISPOSE, rows[0]))
    kernel.commit()


def test_dispose_releases_a_per_node_subtree(wyb):
    kernel = wyb["kernel"]
    root_id, child_id, text_id = kernel.alloc_id(), kernel.alloc_id(), kernel.alloc_id()
    kernel.emit((kernel.OP_CREATE_ELEMENT, root_id, "section"))
    kernel.emit((kernel.OP_CREATE_ELEMENT, child_id, "button"))
    kernel.emit((kernel.OP_CREATE_TEXT, text_id, "x"))
    kernel.emit((kernel.OP_INSERT, root_id, child_id, None))
    kernel.emit((kernel.OP_INSERT, child_id, text_id, None))
    kernel.emit((kernel.OP_LISTEN, child_id, "click"))
    container_id = kernel.alloc_id()
    kernel.emit((kernel.OP_CREATE_ELEMENT, container_id, "div"))
    kernel.emit((kernel.OP_INSERT, container_id, root_id, None))
    kernel.commit()
    kernel.emit((kernel.OP_DISPOSE, root_id))
    kernel.commit()
    assert kernel.get_node(container_id).childNodes == []
    assert [kernel.get_node(i) for i in (root_id, child_id, text_id)] == [None, None, None]
    assert "click" not in kernel._backend._root_listeners


def test_hole_text_reuses_text_anchors_and_replaces_comments(wyb):
    kernel = wyb["kernel"]
    parent_id, text_id, comment_id = kernel.alloc_id(), kernel.alloc_id(), kernel.alloc_id()
    kernel.emit((kernel.OP_CREATE_ELEMENT, parent_id, "p"))
    kernel.emit((kernel.OP_CREATE_TEXT, text_id, " "))
    kernel.emit((kernel.OP_CREATE_COMMENT, comment_id, ""))
    kernel.emit((kernel.OP_INSERT, parent_id, text_id, None))
    kernel.emit((kernel.OP_INSERT, parent_id, comment_id, None))
    kernel.commit()
    placeholder = kernel.get_node(text_id)
    kernel.emit((kernel.OP_HOLE_TEXT, text_id, "hello"))
    kernel.emit((kernel.OP_HOLE_TEXT, comment_id, "world"))
    kernel.commit()
    parent = kernel.get_node(parent_id)
    # A text placeholder is written in place; a comment anchor is replaced by text.
    assert kernel.get_node(text_id) is placeholder
    assert [child.nodeValue for child in parent.childNodes] == ["hello", "world"]
    assert not getattr(kernel.get_node(comment_id), "_is_comment", False)


def test_move_range_moves_a_sibling_run_before_an_anchor(wyb):
    kernel = wyb["kernel"]
    parent_id = kernel.alloc_id()
    kernel.emit((kernel.OP_CREATE_ELEMENT, parent_id, "ul"))
    ids = []
    for label in "abcd":
        node_id = kernel.alloc_id()
        ids.append(node_id)
        kernel.emit((kernel.OP_CREATE_TEXT, node_id, label))
        kernel.emit((kernel.OP_INSERT, parent_id, node_id, None))
    kernel.emit((kernel.OP_MOVE_RANGE, parent_id, ids[2], ids[3], ids[0]))
    kernel.commit()
    assert [child.nodeValue for child in kernel.get_node(parent_id).childNodes] == ["c", "d", "a", "b"]
    kernel.emit((kernel.OP_MOVE_RANGE, parent_id, ids[2], ids[3], None))
    kernel.commit()
    assert [child.nodeValue for child in kernel.get_node(parent_id).childNodes] == ["a", "b", "c", "d"]


def test_claim_static_is_ignored_outside_hydration(wyb):
    kernel = wyb["kernel"]
    parent_id = kernel.alloc_id()
    kernel.emit((kernel.OP_CREATE_ELEMENT, parent_id, "div"))
    kernel.emit((kernel.OP_CLAIM_STATIC, parent_id, "/wyb:nh"))
    kernel.commit()
    assert kernel.get_node(parent_id).childNodes == []
