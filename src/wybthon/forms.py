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

import asyncio
import copy
import inspect
import re
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from .reactivity import _core
from .reactivity._core import Accessor, Signal
from .reactivity._primitives import Setter, create_memo, create_signal

__all__ = [
    "Validator",
    "Field",
    "FormState",
    "AsyncValidator",
    "bind_number",
    "bind_multiselect",
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
type AsyncValidator = Callable[[Any], str | None | Awaitable[str | None]]
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

    __slots__ = (
        "value",
        "error",
        "set_error",
        "touched",
        "set_touched",
        "dirty",
        "validating",
        "_initial",
        "_revision",
        "_validation",
        "_input_error",
    )

    def __init__(self, initial: T) -> None:
        self.value: Signal[T] = Signal(copy.deepcopy(initial))
        self._initial: Signal[T] = Signal(copy.deepcopy(initial))
        self._revision = 0
        self._validation: asyncio.Task[Any] | None = None
        self.validating: Signal[bool] = Signal(False)
        self._input_error: Signal[str | None] = Signal(None)
        self.dirty: Accessor[bool] = create_memo(
            lambda: self._input_error() is not None or self.value() != self._initial()
        )
        if _core._current_owner is not None:
            _core._current_owner._add_cleanup(self._cancel_validation)
        self.error: Accessor[str | None]
        self.set_error: Setter[str | None]
        self.error, self.set_error = create_signal(None)
        self.touched: Accessor[bool]
        self.set_touched: Setter[bool]
        self.touched, self.set_touched = create_signal(False)

    def validate(self, validators: list[Validator]) -> str | None:
        """Validate the current value, mark the field touched, and store the error."""
        self._cancel_validation()
        err = self._input_error._latest() or (validate(self.value._latest(), validators) if validators else None)
        self.set_touched(True)
        self.set_error(err)
        return err

    def _cancel_validation(self) -> None:
        self._revision += 1
        if self._validation is not None and not self._validation.done():
            self._validation.cancel()
        self._validation = None
        self.validating._set(False, _core._O_REVEAL)

    def set_value(self, value: T | Callable[[T], T]) -> T:
        """Stage a value and invalidate any validation for an earlier edit."""
        self._cancel_validation()
        self._input_error._set(None)
        return self.value.set(value)

    def reset(self, value: Any = _core._MISSING) -> None:
        """Reset value, errors, and interaction state; optionally set a new baseline."""
        self._cancel_validation()
        if value is not _core._MISSING:
            self._initial._set(copy.deepcopy(value))
        self.value._set(copy.deepcopy(self._initial._latest()))
        self._input_error._set(None)
        self.set_error(None)
        self.set_touched(False)

    async def validate_async(self, validators: list[AsyncValidator]) -> str | None:
        """Validate the latest edit; stale responses never overwrite newer state."""
        self._cancel_validation()
        revision = self._revision
        value = copy.deepcopy(self.value._latest())
        self.set_touched(True)
        self.validating._set(True, _core._O_REVEAL)

        async def run() -> str | None:
            if self._input_error._latest() is not None:
                return self._input_error._latest()
            for validator in validators:
                result = validator(value)
                message = await result if inspect.isawaitable(result) else result
                if message:
                    return message
            return None

        task = self._validation = asyncio.create_task(run())
        try:
            error = await task
            if revision == self._revision:
                self.set_error(error)
                return error
            return None
        except asyncio.CancelledError:
            if revision == self._revision:
                raise
            return None
        finally:
            if revision == self._revision:
                self._validation = None
                self.validating._set(False, _core._O_REVEAL)

    def __repr__(self) -> str:
        return f"Field(value={self.value.peek()!r}, error={self.error.peek()!r}, touched={self.touched.peek()!r})"


class FormState(dict[str, Field[Any]]):
    """Fields plus aggregate dirty, validating, and submission state."""

    def __init__(self, initial: Mapping[str, Any]) -> None:
        super().__init__((name, Field(value)) for name, value in initial.items())
        self.dirty = create_memo(lambda: any(field.dirty() for field in self.values()))
        self.validating = create_memo(lambda: any(field.validating() for field in self.values()))
        self.submitting = Signal(False)
        self.submit_error: Signal[Exception | None] = Signal(None)

    def data(self) -> dict[str, Any]:
        """Read the current values as a detached mapping."""
        return {name: copy.deepcopy(field.value()) for name, field in self.items()}

    def reset(self, values: Mapping[str, Any] | None = None) -> None:
        """Reset all fields, optionally replacing their initial values."""
        if values is not None and set(values) != set(self):
            raise ValueError("Reset values must contain exactly the form's field names")
        for name, field in self.items():
            field.reset(values[name] if values is not None else _core._MISSING)
        self.submit_error._set(None, _core._O_REVEAL)

    async def submit(
        self, handler: Callable[[dict[str, Any]], Any], *, rules: Mapping[str, list[AsyncValidator]] | None = None
    ) -> Any:
        """Validate and submit a value snapshot, exposing pending and failure state."""
        if self.submitting._latest():
            raise RuntimeError("This form already has a submission in flight")
        self.submitting._set(True, _core._O_REVEAL)
        self.submit_error._set(None, _core._O_REVEAL)
        revisions = {name: field._revision for name, field in self.items()}
        try:
            errors = await asyncio.gather(
                *(field.validate_async((rules or {}).get(name, [])) for name, field in self.items())
            )
            # validate_async increments once when it starts. Any further edit
            # invalidates this submission instead of sending mixed revisions.
            if any(errors) or any(field._revision != revisions[name] + 1 for name, field in self.items()):
                return None
            data = {name: copy.deepcopy(field.value._latest()) for name, field in self.items()}
            result = handler(data)
            return await result if inspect.isawaitable(result) else result
        except Exception as exc:
            self.submit_error._set(exc, _core._O_REVEAL)
            raise
        finally:
            self.submitting._set(False, _core._O_REVEAL)


def form_state(initial: Mapping[str, Any]) -> FormState:
    """Create fields and aggregate form state from initial values."""
    return FormState(initial)


# ----------------- Binding helpers -----------------


def bind_text(
    field: Field[Any],
    *,
    validators: list[Validator] | None = None,
    parse: Callable[[str], Any] | None = None,
    format: Callable[[Any], str] | None = None,
) -> dict[str, Any]:
    """Bind a text input to a field with validation on every `input` event.

    Returns:
        Props to spread onto a text input (`value` + `on_input`). The
        `value` entry is the field's accessor, so programmatic writes
        (`field.set_value(...)`) update the DOM too.
    """
    rules = validators or []

    def on_input(evt: Any) -> None:
        if getattr(evt, "is_composing", False):
            return
        val = evt.target.value if evt.target is not None else ""
        if val is None:
            val = ""
        try:
            val = parse(val) if parse is not None else val
        except (ValueError, TypeError) as exc:
            field._cancel_validation()
            message = str(exc) or "Enter a valid value"
            field._input_error._set(message)
            field.set_error(message)
            field.set_touched(True)
            return
        field.set_value(val)
        field.set_touched(True)
        field.set_error(validate(val, rules))

    return {
        "value": (lambda: format(field.value())) if format else field.value,
        "on_input": on_input,
        "on_compositionend": on_input,
    }


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


def bind_number(field: Field[float | None], *, validators: list[Validator] | None = None) -> dict[str, Any]:
    """Bind a numeric input, preserving an empty value as None."""
    return {
        "type": "number",
        "step": "any",
        **bind_text(
            field,
            validators=validators,
            parse=lambda text: float(text) if text.strip() else None,
            format=lambda value: "" if value is None else str(value),
        ),
    }


def bind_multiselect(field: Field[list[str]]) -> dict[str, Any]:
    """Bind all selected option values without per-option bridge reads."""

    def changed(evt: Any) -> None:
        field.set_value(list(evt.target.selected_values))
        field.set_touched(True)
        field.set_error(None)

    return {"multiple": True, "selected_values": field.value, "on_change": changed}


def on_submit(handler: Callable[[dict[str, Field[Any]]], Any], form: dict[str, Field[Any]]) -> Callable[[Any], Any]:
    """Create a submit handler that prevents default and forwards to `handler`."""

    def _onsubmit(evt: Any) -> Any:
        evt.prevent_default()
        return handler(form)

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

    def _onsubmit(evt: Any) -> Any:
        evt.prevent_default()
        is_valid, _ = validate_form(form, rules)
        return handler(form) if is_valid else None

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
