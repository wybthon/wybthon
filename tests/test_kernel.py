def test_create_element_op(wyb):
    """CREATE_ELEMENT produces the expected stub-DOM state after commit()."""
    kernel = wyb["kernel"]

    node_id = kernel.alloc_id()
    # Queue the operation: [OP_CREATE_ELEMENT, id, tag]
    kernel.emit((kernel.OP_CREATE_ELEMENT, node_id, "div"))
    kernel.commit()

    backend = kernel._backend
    assert node_id in backend._nodes
    assert backend._nodes[node_id].tag == "div"


def test_set_attr_removes_with_none(wyb):
    """SET_ATTR with None removes the attribute."""
    kernel = wyb["kernel"]

    node_id = kernel.alloc_id()
    kernel.emit((kernel.OP_CREATE_ELEMENT, node_id, "div"))
    # Add an attribute: [OP_SET_ATTR, id, name, value]
    kernel.emit((kernel.OP_SET_ATTR, node_id, "id", "my-div"))
    kernel.commit()

    backend = kernel._backend
    node = backend._nodes[node_id]
    assert node.getAttribute("id") == "my-div"

    # Remove the attribute by passing None
    kernel.emit((kernel.OP_SET_ATTR, node_id, "id", None))
    kernel.commit()
    assert node.getAttribute("id") is None


def test_insert_with_none_anchor_appends(wyb):
    """INSERT with a None anchor appends to the parent."""
    kernel = wyb["kernel"]

    parent_id = kernel.alloc_id()
    child_id = kernel.alloc_id()

    kernel.emit((kernel.OP_CREATE_ELEMENT, parent_id, "div"))
    kernel.emit((kernel.OP_CREATE_ELEMENT, child_id, "span"))

    # [OP_INSERT, parent_id, child_id, anchor_id_or_None]
    kernel.emit((kernel.OP_INSERT, parent_id, child_id, None))
    kernel.commit()

    backend = kernel._backend
    parent = backend._nodes[parent_id]
    child = backend._nodes[child_id]
    assert child in parent.childNodes


def test_remove_op(wyb):
    """REMOVE deletes the node from its parent."""
    kernel = wyb["kernel"]

    parent_id = kernel.alloc_id()
    child_id = kernel.alloc_id()

    kernel.emit((kernel.OP_CREATE_ELEMENT, parent_id, "div"))
    kernel.emit((kernel.OP_CREATE_ELEMENT, child_id, "span"))
    kernel.emit((kernel.OP_INSERT, parent_id, child_id, None))
    kernel.commit()

    # [OP_REMOVE, id]
    kernel.emit((kernel.OP_REMOVE, child_id))
    kernel.commit()

    backend = kernel._backend
    parent = backend._nodes[parent_id]
    child = backend._nodes[child_id]
    assert child not in parent.childNodes
