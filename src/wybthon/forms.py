"""Form state, validation helpers, and accessibility attribute utilities.

This module gives you a small but complete toolkit for building
controlled form components on top of Wybthon's reactive primitives:

- [`form_state`][wybthon.form_state] creates a map of
  [`Field`][wybthon.Field] entries (each backed by signals for value,
  error, and touched flags).
- [`bind_text`][wybthon.bind_text],
  [`bind_checkbox`][wybthon.bind_checkbox], and
  [`bind_select`][wybthon.bind_select] return prop dictionaries you can
  spread onto inputs.
- [`on_submit`][wybthon.on_submit] and
  [`on_submit_validated`][wybthon.on_submit_validated] wrap submit
  handlers with the right `preventDefault` / validation glue.
- Validator helpers ([`required`][wybthon.required],
  [`min_length`][wybthon.min_length],
  [`max_length`][wybthon.max_length], [`email`][wybthon.email]) compose
  with [`validate`][wybthon.validate],
  [`validate_field`][wybthon.validate_field], and
  [`validate_form`][wybthon.validate_form].
- [`a11y_control_attrs`][wybthon.a11y_control_attrs] and
  [`error_message_attrs`][wybthon.error_message_attrs] generate ARIA
  attributes (reactively) so error messages are announced correctly.

Example:
    ```python
    form = form_state({"name": "", "email": ""})
    rules = {"name": [required()], "email": [required(), email()]}

    def save(fields):
        print({k: f.value() for k, f in fields.items()})

    form(
        input_(**bind_text(form["name"], validators=rules["name"])),
        span(form["name"].error, **error_message_attrs(id="name-error")),
        button("Save", type="submit"),
        on_submit=on_submit_validated(rules, save, form),
    )
    ```

See Also:
    - [Forms guide](../concepts/forms.md)
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from .reactivity._core import Accessor
from .reactivity._primitives import Setter, create_signal

__all__ = [
    "Validator",
    "Field",
    "form_state",
    "bind_text",
    "bind_checkbox",
    "bind_select",
    "on_submit",
    "on_submit_validated",
    "rules_from_schema",
    "validate",
    "validate_field",
    "validate_form",
    "required",
    "min_length",
    "max_length",
    "email",
    "a11y_control_attrs",
    "error_message_attrs",
]

# ----------------- Validation primitives -----------------

type Validator = Callable[[Any], str | None]
"""A validator takes a value and returns an error message, or `None` when valid."""


def required(message: str = "This field is required") -> Validator:
    """Validate that a value is present and non-empty.

    Returns a validator that returns `message` for `None` or blank
    strings (after `strip()`), otherwise `None`.
    """

    def _v(value: Any) -> str | None:
        if value is None:
            return message
        if isinstance(value, str) and value.strip() == "":
            return message
        return None

    return _v


def min_length(n: int, message: str | None = None) -> Validator:
    """Validate that the stringified value length is at least `n`."""
    msg = message or f"Minimum length is {n}"

    def _v(value: Any) -> str | None:
        return None if (value is not None and len(str(value)) >= n) else msg

    return _v


def max_length(n: int, message: str | None = None) -> Validator:
    """Validate that the stringified value length is at most `n`."""
    msg = message or f"Maximum length is {n}"

    def _v(value: Any) -> str | None:
        return None if (value is not None and len(str(value)) <= n) else msg

    return _v


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def email(message: str = "Invalid email address") -> Validator:
    """Validate a basic email address format with a lightweight regex.

    Accepts `None` and empty strings as valid so it can be combined
    with [`required`][wybthon.required], which handles the missing
    case explicitly.
    """

    def _v(value: Any) -> str | None:
        if value is None or str(value).strip() == "":
            return None
        return None if _EMAIL_RE.match(str(value)) else message

    return _v


def validate(value: Any, validators: list[Validator]) -> str | None:
    """Return the first validation error, or `None` when all validators pass."""
    for v in validators:
        msg = v(value)
        if msg:
            return msg
    return None


# ----------------- Form state -----------------


class Field[T]:
    """Reactive state for one form field: value, error, and touched.

    Attributes:
        value: Accessor for the current input value.
        set_value: Setter for the value.
        error: Accessor for the latest validation error, or `None`.
        set_error: Setter for the error.
        touched: Accessor that's `True` once the user has interacted
            with the field, so error display can wait until they have.
        set_touched: Setter for the touched flag.
    """

    __slots__ = ("value", "set_value", "error", "set_error", "touched", "set_touched")

    def __init__(self, initial: T) -> None:
        self.value: Accessor[T]
        self.set_value: Setter[T]
        self.value, self.set_value = create_signal(initial)
        self.error: Accessor[str | None]
        self.set_error: Setter[str | None]
        self.error, self.set_error = create_signal(None)
        self.touched: Accessor[bool]
        self.set_touched: Setter[bool]
        self.touched, self.set_touched = create_signal(False)

    def validate(self, validators: list[Validator]) -> str | None:
        """Validate the current value, mark the field touched, and store the error."""
        err = validate(self.value.peek(), validators) if validators else None
        self.set_touched(True)
        self.set_error(err)
        return err

    def __repr__(self) -> str:
        return f"Field(value={self.value.peek()!r}, error={self.error.peek()!r}, touched={self.touched.peek()!r})"


def form_state(initial: dict[str, Any]) -> dict[str, Field[Any]]:
    """Create a form state map from a dict of initial values.

    Returns:
        A dict mapping each field name to a fresh [`Field`][wybthon.Field].
    """
    return {name: Field(val) for name, val in initial.items()}


# ----------------- Binding helpers -----------------


def bind_text(field: Field[Any], *, validators: list[Validator] | None = None) -> dict[str, Any]:
    """Bind a text input to a field with validation on every `input` event.

    Returns:
        Props to spread onto a text input (`value` + `on_input`). The
        `value` entry is the field's accessor, so programmatic writes
        (`field.set_value(...)`) update the DOM too.
    """
    rules = validators or []

    def on_input(evt: Any) -> None:
        val = evt.target.value if evt.target is not None else ""
        if val is None:
            val = ""
        field.set_value(val)
        field.set_touched(True)
        field.set_error(validate(val, rules))

    return {"value": field.value, "on_input": on_input}


def bind_checkbox(field: Field[bool]) -> dict[str, Any]:
    """Bind a checkbox input to a boolean field (`checked` + `on_change`)."""

    def on_change(evt: Any) -> None:
        checked = bool(evt.target.checked) if evt.target is not None else False
        field.set_value(checked)
        field.set_touched(True)
        field.set_error(None)

    return {"checked": lambda: bool(field.value()), "on_change": on_change}


def bind_select(field: Field[Any]) -> dict[str, Any]:
    """Bind a `<select>` element to a field (`value` + `on_change`)."""

    def on_change(evt: Any) -> None:
        val = evt.target.value if evt.target is not None else ""
        if val is None:
            val = ""
        field.set_value(val)
        field.set_touched(True)
        field.set_error(None)

    return {"value": field.value, "on_change": on_change}


def on_submit(handler: Callable[[dict[str, Field[Any]]], Any], form: dict[str, Field[Any]]) -> Callable[[Any], Any]:
    """Create a submit handler that prevents default and forwards to `handler`."""

    def _onsubmit(evt: Any) -> None:
        evt.prevent_default()
        handler(form)

    return _onsubmit


# ----------------- Aggregated validation and a11y helpers -----------------


def validate_field(field: Field[Any], validators: list[Validator] | None = None) -> str | None:
    """Validate a single field and update its `error` and `touched` signals."""
    return field.validate(validators or [])


def validate_form(form: dict[str, Field[Any]], rules: dict[str, list[Validator]]) -> tuple[bool, dict[str, str | None]]:
    """Validate every field in a form against a rules map.

    Marks each listed field touched and stores its error as a side
    effect.

    Returns:
        A `(is_valid, errors)` tuple where `errors` maps each field
        name to its current error message (or `None`).
    """
    errors: dict[str, str | None] = {}
    all_valid = True
    for name, validators in rules.items():
        field = form.get(name)
        if field is None:
            errors[name] = None
            continue
        err = field.validate(validators or [])
        errors[name] = err
        if err is not None:
            all_valid = False
    return all_valid, errors


def on_submit_validated(
    rules: dict[str, list[Validator]],
    handler: Callable[[dict[str, Field[Any]]], Any],
    form: dict[str, Field[Any]],
) -> Callable[[Any], Any]:
    """Submit handler that validates the whole form before calling `handler`."""

    def _onsubmit(evt: Any) -> None:
        evt.prevent_default()
        is_valid, _ = validate_form(form, rules)
        if is_valid:
            handler(form)

    return _onsubmit


def rules_from_schema(schema: dict[str, dict[str, Any]]) -> dict[str, list[Validator]]:
    """Build a validators map from a small declarative schema.

    Supported per-field keys:

    - `required`: `bool` or `str` (a string is used as the message).
    - `min_length`: `int`, with optional `min_length_message`.
    - `max_length`: `int`, with optional `max_length_message`.
    - `email`: `bool` or `str` (a string is used as the message).

    Example:
        ```python
        rules_from_schema({
            "name": {"required": True, "min_length": 2},
            "email": {"email": True},
        })
        ```
    """
    rules: dict[str, list[Validator]] = {}
    for field_name, spec in schema.items():
        vlist: list[Validator] = []
        req = spec.get("required")
        if req:
            vlist.append(required(req if isinstance(req, str) else "This field is required"))
        if spec.get("min_length") is not None:
            vlist.append(min_length(int(spec["min_length"]), spec.get("min_length_message")))
        if spec.get("max_length") is not None:
            vlist.append(max_length(int(spec["max_length"]), spec.get("max_length_message")))
        em = spec.get("email")
        if em:
            vlist.append(email(em if isinstance(em, str) else "Invalid email address"))
        rules[field_name] = vlist
    return rules


def a11y_control_attrs(field: Field[Any], *, described_by_id: str | None = None) -> dict[str, Any]:
    """Reactive ARIA attributes for a control bound to a field.

    - `aria-invalid` is `"true"` while the field has an error.
    - `aria-describedby` references `described_by_id` while an error
      is present, so screen readers announce the message.

    Returns:
        Props to spread onto the control (reactive values).
    """
    attrs: dict[str, Any] = {"aria_invalid": lambda: "true" if field.error() is not None else "false"}
    if described_by_id:
        attrs["aria_describedby"] = lambda: described_by_id if field.error() is not None else None
    return attrs


def error_message_attrs(*, id: str) -> dict[str, Any]:
    """Attributes for an accessible error-message container (a polite live region)."""
    return {"id": id, "role": "alert", "aria_live": "polite"}
