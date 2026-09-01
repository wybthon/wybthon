from wybthon import (
    a11y_control_attrs,
    bind_checkbox,
    bind_select,
    bind_text,
    email,
    error_message_attrs,
    form_state,
    min_length,
    on_submit,
    on_submit_validated,
    required,
    rules_from_schema,
    validate_form,
)


class DummyTarget:
    """Stand-in for ``DomEvent.target`` exposing ``value``/``checked`` directly.

    Mirrors the ergonomic ``Element`` wrapper API so tests can assert
    against the same handler surface real handlers see.
    """

    def __init__(self, value=None, checked=False):
        self.value = value
        self.checked = checked


class DummyEvent:
    def __init__(self, value=None, checked=False):
        self.type = None
        self.target = DummyTarget(value=value, checked=checked)
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


def test_on_submit_calls_handler_and_prevents_default():
    form = form_state({"name": "Alice"})
    called = {"count": 0, "form": None}

    def handler(f):
        called["count"] += 1
        called["form"] = f

    submit = on_submit(handler, form)

    evt = DummyEvent()
    submit(evt)

    assert called["count"] == 1
    assert called["form"] is form


def test_bind_text_with_validators_updates_error():
    form = form_state({"name": ""})
    name_field = form["name"]

    bind = bind_text(name_field, validators=[required(), min_length(3)])

    evt = DummyEvent(value="ab")
    bind["on_input"](evt)
    assert name_field.error.get() == "Minimum length is 3"

    evt = DummyEvent(value="Alice")
    bind["on_input"](evt)
    assert name_field.error.get() is None


def test_error_message_attrs_returns_polite_live_region():
    attrs = error_message_attrs(id="name-err")
    assert attrs["id"] == "name-err"
    assert attrs["role"] == "alert"
    assert attrs["aria-live"] == "polite"


def test_rules_from_schema_uses_custom_messages():
    form = form_state({"name": "", "email": "bad"})
    schema = {
        "name": {"required": "Name is required", "min_length": 3, "min_length_message": "Name is too short"},
        "email": {"email": "Bad email address"},
    }
    rules = rules_from_schema(schema)

    is_valid, errors = validate_form(form, rules)
    assert is_valid is False
    assert errors["name"] == "Name is required"
    assert errors["email"] == "Bad email address"

    form["name"].value.set("ab")
    is_valid2, errors2 = validate_form(form, rules)
    assert is_valid2 is False
    assert errors2["name"] == "Name is too short"


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


def test_rules_from_schema_builds_rules_and_validates():
    form = form_state({"name": "", "email": ""})
    schema = {
        "name": {"required": True, "min_length": 2},
        "email": {"email": True},
    }
    rules = rules_from_schema(schema)

    # initial: name invalid, email empty but allowed by email validator
    is_valid, errors = validate_form(form, rules)
    assert is_valid is False
    assert errors["name"] is not None
    assert errors["email"] is None

    # fill values and revalidate
    form["name"].value.set("Al")
    form["email"].value.set("user@example.com")
    is_valid2, errors2 = validate_form(form, rules)
    assert is_valid2 is True
    assert errors2["name"] is None
    assert errors2["email"] is None
