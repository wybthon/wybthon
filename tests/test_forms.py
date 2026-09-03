from types import SimpleNamespace

from conftest import collect_texts

from wybthon.forms import (
    Field,
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
    validate_field,
    validate_form,
)
from wybthon.html import form, input_, option, select, span
from wybthon.reactivity import flush


def texts(node):
    return [t for t in collect_texts(node) if t]


class FakeEvent:
    def __init__(self, **target):
        self.target = SimpleNamespace(**target) if target else None
        self.prevented = False

    def prevent_default(self):
        self.prevented = True


def test_form_state_creates_fields_with_accessor_setter_pairs():
    fields = form_state({"name": "", "agree": False})
    assert set(fields) == {"name", "agree"}
    assert all(isinstance(f, Field) for f in fields.values())
    name = fields["name"]
    assert name.value() == ""
    assert name.error() is None
    assert name.touched() is False
    assert fields["agree"].value() is False
    name.set_value("Ada")
    name.set_touched(True)
    name.set_error("bad")
    flush()
    assert (name.value(), name.touched(), name.error()) == ("Ada", True, "bad")
    assert repr(name) == "Field(value='Ada', error='bad', touched=True)"


def test_bind_text_returns_value_accessor_and_input_handler():
    field = form_state({"name": ""})["name"]
    props = bind_text(field)
    assert set(props) == {"value", "on_input"}
    assert props["value"] is field.value
    props["on_input"](FakeEvent(value="Grace"))
    flush()
    assert field.value() == "Grace"
    assert field.touched() is True
    assert field.error() is None
    props["on_input"](FakeEvent(value=None))
    flush()
    assert field.value() == ""


def test_bind_text_with_validators_sets_error():
    field = form_state({"name": ""})["name"]
    props = bind_text(field, validators=[required(), min_length(3)])
    props["on_input"](FakeEvent(value=""))
    flush()
    assert field.error() == "This field is required"
    props["on_input"](FakeEvent(value="ab"))
    flush()
    assert field.error() == "Minimum length is 3"
    props["on_input"](FakeEvent(value="abc"))
    flush()
    assert field.error() is None


def test_bind_checkbox_reads_checked_and_reflects_value():
    field = form_state({"agree": False})["agree"]
    field.set_error("stale")
    flush()
    props = bind_checkbox(field)
    assert set(props) == {"checked", "on_change"}
    assert props["checked"]() is False
    props["on_change"](FakeEvent(checked=True))
    flush()
    assert field.value() is True
    assert props["checked"]() is True
    assert field.touched() is True
    assert field.error() is None
    props["on_change"](FakeEvent(checked=0))
    flush()
    assert field.value() is False


def test_bind_select_reads_value():
    field = form_state({"color": "red"})["color"]
    props = bind_select(field)
    assert set(props) == {"value", "on_change"}
    assert props["value"] is field.value
    props["on_change"](FakeEvent(value="blue"))
    flush()
    assert field.value() == "blue"
    assert field.touched() is True


def test_field_validate_marks_touched_and_stores_error():
    field = Field("x")
    assert field.validate([min_length(2)]) == "Minimum length is 2"
    flush()
    assert field.touched() is True
    assert field.error() == "Minimum length is 2"
    field.set_value("xy")
    flush()
    assert field.validate([min_length(2)]) is None
    flush()
    assert field.error() is None
    assert validate_field(field, [required()]) is None
    assert validate_field(field) is None


def test_on_submit_prevents_default_and_passes_form():
    fields = form_state({"name": "Ada"})
    received = []
    handler = on_submit(received.append, fields)
    evt = FakeEvent()
    handler(evt)
    assert evt.prevented is True
    assert received == [fields]
    assert received[0]["name"].value() == "Ada"


def test_on_submit_validated_only_calls_handler_when_valid():
    fields = form_state({"name": "", "mail": "nope"})
    rules = {"name": [required()], "mail": [email()]}
    received = []
    handler = on_submit_validated(rules, received.append, fields)

    evt = FakeEvent()
    handler(evt)
    flush()
    assert evt.prevented is True
    assert received == []
    assert fields["name"].error() == "This field is required"
    assert fields["mail"].error() == "Invalid email address"
    assert fields["name"].touched() is True and fields["mail"].touched() is True

    fields["name"].set_value("Ada")
    fields["mail"].set_value("ada@example.com")
    flush()
    handler(FakeEvent())
    flush()
    assert received == [fields]
    assert fields["name"].error() is None
    assert fields["mail"].error() is None


def test_validate_form_reports_per_field_errors_and_ignores_unknown_fields():
    fields = form_state({"name": "", "age": "42"})
    rules = {"name": [required()], "age": [min_length(1)], "missing": [required()]}
    ok, errors = validate_form(fields, rules)
    assert ok is False
    assert errors == {"name": "This field is required", "age": None, "missing": None}
    fields["name"].set_value("Ada")
    flush()
    ok, errors = validate_form(fields, rules)
    assert ok is True
    assert errors["name"] is None


def test_rules_from_schema_builds_validators():
    rules = rules_from_schema(
        {
            "name": {"required": "Name please", "min_length": 2, "max_length": 4, "max_length_message": "Too long"},
            "mail": {"email": True},
            "free": {},
        }
    )
    assert set(rules) == {"name", "mail", "free"}
    assert rules["free"] == []
    name_rules = rules["name"]
    assert len(name_rules) == 3
    assert [v("") for v in name_rules][0] == "Name please"
    assert [v("a") for v in name_rules][1] == "Minimum length is 2"
    assert [v("abcde") for v in name_rules][2] == "Too long"
    assert rules["mail"][0]("bad") == "Invalid email address"
    assert rules["mail"][0]("ok@example.com") is None


def test_a11y_control_attrs_are_reactive():
    field = Field("")
    attrs = a11y_control_attrs(field, described_by_id="e")
    assert set(attrs) == {"aria_invalid", "aria_describedby"}
    assert attrs["aria_invalid"]() == "false"
    assert attrs["aria_describedby"]() is None
    field.set_error("Required")
    flush()
    assert attrs["aria_invalid"]() == "true"
    assert attrs["aria_describedby"]() == "e"
    assert set(a11y_control_attrs(field)) == {"aria_invalid"}


def test_error_message_attrs():
    assert error_message_attrs(id="name-error") == {"id": "name-error", "role": "alert", "aria_live": "polite"}


def test_bound_input_end_to_end_in_dom(wyb, root_element):
    fields = form_state({"name": "", "color": "red", "agree": False})
    rules = {"name": [required(), min_length(2)]}
    saved = []
    name_attrs = {
        **bind_text(fields["name"], validators=rules["name"]),
        **a11y_control_attrs(fields["name"], described_by_id="e"),
    }
    root = wyb["reconciler"].render(
        form(
            input_(**name_attrs),
            span(fields["name"].error, **error_message_attrs(id="e")),
            select(option("red", value="red"), option("blue", value="blue"), **bind_select(fields["color"])),
            input_(type="checkbox", **bind_checkbox(fields["agree"])),
            on_submit=on_submit_validated(rules, lambda f: saved.append(f["name"].value()), fields),
        ),
        root_element,
    )
    backend = wyb["kernel"]._backend
    frm = root_element.element.childNodes[0]
    inp, err, sel, chk = [n for n in frm.childNodes if n.tag]
    assert inp.attributes["aria-invalid"] == "false"
    assert "aria-describedby" not in inp.attributes
    assert err.attributes == {"id": "e", "role": "alert", "aria-live": "polite"}
    assert inp.value == ""

    backend.dispatch("submit", frm)
    assert saved == []
    assert texts(err) == ["This field is required"]
    assert inp.attributes["aria-invalid"] == "true"
    assert inp.attributes["aria-describedby"] == "e"

    inp.value = "A"
    backend.dispatch("input", inp)
    assert fields["name"].value() == "A"
    assert texts(err) == ["Minimum length is 2"]

    inp.value = "Ab"
    backend.dispatch("input", inp)
    assert fields["name"].value() == "Ab"
    assert texts(err) == []
    assert inp.attributes["aria-invalid"] == "false"
    assert "aria-describedby" not in inp.attributes

    sel.value = "blue"
    backend.dispatch("change", sel)
    assert fields["color"].value() == "blue"

    assert chk.checked is False
    chk.checked = True
    backend.dispatch("change", chk)
    assert fields["agree"].value() is True

    backend.dispatch("submit", frm)
    assert saved == ["Ab"]

    # Programmatic writes flow back into the DOM property.
    fields["name"].set_value("Zed")
    flush()
    assert inp.value == "Zed"
    root.dispose()
