"""Tests for the kernel-delegated event system.

Handlers are registered per node id with batched ``LISTEN``/``UNLISTEN``
ops; the backend owns the per-type root listeners and walks the ancestor
chain natively on dispatch, calling into Python once per matched handler
with a JSON payload.
"""

from conftest import StubNode


def test_domevent_payload_shape_and_methods():
    from wybthon.events import DomEvent

    evt = DomEvent(
        {
            "type": "click",
            "value": "abc",
            "checked": True,
            "key": "Enter",
            "metaKey": True,
            "button": 1,
        }
    )

    assert evt.type == "click"
    assert evt.target.value == "abc"
    assert evt.target.checked is True
    assert evt.key == "Enter"
    assert evt.meta_key is True
    assert evt.button == 1
    assert evt.alt_key is False

    evt.prevent_default()
    evt.stop_propagation()
    assert evt._default_prevented is True
    assert evt._stopped is True


def test_event_prop_normalization():
    from wybthon.events import _event_prop_to_type

    assert _event_prop_to_type("on_click") == "click"
    assert _event_prop_to_type("onClick") == "click"
    assert _event_prop_to_type("onclick") == "click"
    assert _event_prop_to_type("on_input") == "input"
    assert _event_prop_to_type("onInput") == "input"


def test_root_listener_refcounting(wyb, browser_stubs):
    """Root listeners install on first LISTEN of a type and tear down at zero."""
    _saved, doc = browser_stubs
    kernel = wyb["kernel"]
    events = wyb["events"]

    node = StubNode(tag="button")
    nid = kernel.adopt(node)

    assert "click" not in doc._listeners

    events.set_handler(nid, "on_click", lambda e: None)
    kernel.commit()
    assert len(doc._listeners.get("click", ())) == 1

    # Replacing the handler must not add another root listener.
    events.set_handler(nid, "on_click", lambda e: None)
    kernel.commit()
    assert len(doc._listeners.get("click", ())) == 1

    events.set_handler(nid, "on_click", None)
    kernel.commit()
    assert not doc._listeners.get("click")


def test_release_clears_listener_bookkeeping(wyb, browser_stubs):
    """Releasing a node drops its handler types and tears down root listeners."""
    _saved, doc = browser_stubs
    kernel = wyb["kernel"]
    events = wyb["events"]

    node = StubNode(tag="input")
    nid = kernel.adopt(node)

    events.set_handler(nid, "on_click", lambda e: None)
    events.set_handler(nid, "on_input", lambda e: None)
    kernel.commit()
    assert len(doc._listeners.get("click", ())) == 1
    assert len(doc._listeners.get("input", ())) == 1

    events.remove_handlers_for(nid)
    kernel.emit((kernel.OP_RELEASE, [nid]))
    kernel.commit()
    assert not doc._listeners.get("click")
    assert not doc._listeners.get("input")
    assert events._handlers.get(nid) is None


def test_dispatch_bubbles_and_carries_payload(wyb):
    """Dispatch walks ancestors, building DomEvents from the payload."""
    kernel = wyb["kernel"]
    events = wyb["events"]
    backend = kernel._backend

    parent = StubNode(tag="div")
    child = StubNode(tag="input")
    child.value = "typed"
    parent.appendChild(child)
    parent_id = kernel.adopt(parent)
    child_id = kernel.adopt(child)

    seen = []
    events.set_handler(parent_id, "on_input", lambda e: seen.append(("parent", e.target.value)))
    events.set_handler(child_id, "on_input", lambda e: seen.append(("child", e.target.value)))
    kernel.commit()

    backend.dispatch("input", child)
    assert seen == [("child", "typed"), ("parent", "typed")]


def test_dispatch_stop_propagation_halts_walk(wyb):
    kernel = wyb["kernel"]
    events = wyb["events"]
    backend = kernel._backend

    parent = StubNode(tag="div")
    child = StubNode(tag="button")
    parent.appendChild(child)
    parent_id = kernel.adopt(parent)
    child_id = kernel.adopt(child)

    seen = []

    def child_handler(e):
        seen.append("child")
        e.stop_propagation()

    events.set_handler(parent_id, "on_click", lambda e: seen.append("parent"))
    events.set_handler(child_id, "on_click", child_handler)
    kernel.commit()

    backend.dispatch("click", child)
    assert seen == ["child"]
