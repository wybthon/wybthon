from types import SimpleNamespace


def make_dummy_js_event(**kwargs):
    target = kwargs.pop("target", SimpleNamespace(getAttribute=lambda n: None))
    defaults = {
        "type": "click",
        "target": target,
        "preventDefault": lambda: None,
        "stopPropagation": lambda: None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_domevent_shape_and_methods_imports_without_browser():
    # Importing DomEvent should work even without js/pyodide
    from wybthon.events import DomEvent

    js_evt = make_dummy_js_event()
    evt = DomEvent(js_evt)

    assert evt.type == "click"
    assert evt.target is not None
    # Calling these should not raise outside browser
    evt.prevent_default()
    evt.stop_propagation()


def test_event_prop_normalization():
    from wybthon.events import _event_prop_to_type

    assert _event_prop_to_type("on_click") == "click"
    assert _event_prop_to_type("onClick") == "click"
    assert _event_prop_to_type("onclick") == "click"
    assert _event_prop_to_type("on_input") == "input"
    assert _event_prop_to_type("onInput") == "input"
