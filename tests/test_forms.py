from types import SimpleNamespace

from wybthon import (
    a11y_control_attrs,
    bind_checkbox,
    bind_select,
    bind_text,
    email,
    form_state,
    on_submit_validated,
    required,
    validate_form,
)


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


def test_validate_form_and_a11y_attrs():
    form = form_state({"name": "", "email": ""})
    rules = {"name": [required()], "email": [email()]}

    # Initially, name is empty => required error; email empty => no error due to optional email
    is_valid, errors = validate_form(form, rules)
    assert is_valid is False
    assert errors["name"] is not None
    assert errors["email"] is None

    # a11y control reflects error state
    name_attrs = a11y_control_attrs(form["name"], described_by_id="name-err")
    assert name_attrs.get("aria-invalid") == "true"

    # Fix the name, then the form should be valid
    form["name"].value.set("Alice")
    is_valid2, errors2 = validate_form(form, rules)
    assert is_valid2 is True
    assert errors2["name"] is None


def test_on_submit_validated_calls_handler_only_when_valid():
    # Arrange form and rules
    form = form_state({"name": ""})
    rules = {"name": [required()]}
    called = {"count": 0}

    def handler(_form):
        called["count"] += 1

    submit = on_submit_validated(rules, handler, form)

    # Event with prevent_default no-op
    evt = DummyEvent(value=None)

    # Invalid initially
    submit(evt)
    assert called["count"] == 0

    # Make valid and submit again
    form["name"].value.set("Ok")
    submit(evt)
    assert called["count"] == 1
