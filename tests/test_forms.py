from types import SimpleNamespace

from wybthon import bind_checkbox, bind_select, bind_text, form_state


class DummyTarget:
    def __init__(self, value=None, checked=False):
        self.value = value
        self.checked = checked


class DummyEvent:
    def __init__(self, value=None, checked=False):
        self._js_event = None
        self.type = None
        self.target = SimpleNamespace(element=DummyTarget(value=value, checked=checked))
        self.current_target = None
        self._stopped = False

    def prevent_default(self):
        pass


def test_bind_text_updates_value_and_error():
    form = form_state({"name": ""})
    name_field = form["name"]

    bind = bind_text(name_field)
    # Simulate input event
    evt = DummyEvent(value="Alice")
    bind["on_input"](evt)

    assert name_field.value.get() == "Alice"
    assert name_field.touched.get() is True


def test_bind_checkbox_updates_value():
    form = form_state({"newsletter": False})
    field = form["newsletter"]

    bind = bind_checkbox(field)
    evt = DummyEvent(checked=True)
    bind["on_change"](evt)

    assert field.value.get() is True


def test_bind_select_updates_value():
    form = form_state({"choice": ""})
    field = form["choice"]

    bind = bind_select(field)
    evt = DummyEvent(value="b")
    bind["on_change"](evt)

    assert field.value.get() == "b"
