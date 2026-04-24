"""Form state, validation helpers, and accessibility attribute utilities.

This module gives you a small but complete toolkit for building
controlled form components on top of Wybthon's reactive primitives:

- [`form_state`][wybthon.form_state] creates a map of
  [`FieldState`][wybthon.FieldState] entries (each backed by signals
  for value, error, and touched flags).
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
  attributes so error messages are announced correctly.

See Also:
    - [Forms guide](../concepts/forms.md)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from .reactivity import Signal

__all__ = [
    "Validator",
    "FieldState",
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

Validator = Callable[[Any], Optional[str]]


def required(message: str = "This field is required") -> Validator:
    """Validate that a value is present and non-empty.

    Args:
        message: Error message used when the value is missing or
            blank.

    Returns:
        A validator that returns `message` for `None` or empty strings
        (after `strip()`), otherwise `None`.
    """

    def _v(value: Any) -> Optional[str]:
        if value is None:
            return message
        if isinstance(value, str) and value.strip() == "":
            return message
        return None

    return _v


def min_length(n: int, message: Optional[str] = None) -> Validator:
    """Validate that the stringified value length is at least `n`.

    Args:
        n: Minimum allowed length.
        message: Optional override for the default error message.

    Returns:
        A validator that returns the message when `len(str(value)) <
        n` or when `value` is `None`, otherwise `None`.
    """
    msg = message or f"Minimum length is {n}"

    def _v(value: Any) -> Optional[str]:
        try:
            return None if (value is not None and len(str(value)) >= n) else msg
        except Exception:
            return msg

    return _v


def max_length(n: int, message: Optional[str] = None) -> Validator:
    """Validate that the stringified value length is at most `n`.

    Args:
        n: Maximum allowed length.
        message: Optional override for the default error message.

    Returns:
        A validator that returns the message when `len(str(value)) >
        n` or when `value` is `None`, otherwise `None`.
    """
    msg = message or f"Maximum length is {n}"

    def _v(value: Any) -> Optional[str]:
        try:
            return None if (value is not None and len(str(value)) <= n) else msg
        except Exception:
            return msg

    return _v


def email(message: str = "Invalid email address") -> Validator:
    """Validate a basic email address format with a lightweight regex.

    The validator accepts `None` and empty strings as valid so it can
    be combined with [`required`][wybthon.required] (which handles the
    "missing" case explicitly).

    Args:
        message: Error message used when the value does not match.

    Returns:
        A validator returning `message` on bad input, otherwise
        `None`.
    """
    import re

    pattern = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    def _v(value: Any) -> Optional[str]:
        if value is None or str(value).strip() == "":
            return None
        return None if pattern.match(str(value)) else message

    return _v


def validate(value: Any, validators: List[Validator]) -> Optional[str]:
    """Return the first validation error, or `None` when all validators pass.

    Args:
        value: Value to validate.
        validators: Ordered list of validators applied with
            short-circuit semantics.

    Returns:
        The error message from the first failing validator, or `None`
        if every validator returns `None`.
    """
    for v in validators:
        msg = v(value)
        if msg:
            return msg
    return None


# ----------------- Form state -----------------


@dataclass
class FieldState:
    """Signals representing a field's value, error message, and touched state.

    Attributes:
        value: Signal holding the current input value.
        error: Signal holding the latest validation error message, or
            `None` when valid.
        touched: Signal that becomes `True` once the user has
            interacted with the field. Useful for delaying error
            display until the user has had a chance to respond.
    """

    value: Signal[Any]
    error: Signal[Optional[str]]
    touched: Signal[bool]


def form_state(initial: Dict[str, Any]) -> Dict[str, FieldState]:
    """Create a form state map from a dict of initial values.

    Args:
        initial: Mapping of field name to initial value.

    Returns:
        A dict mapping each field name to a freshly-created
        [`FieldState`][wybthon.FieldState].
    """
    state: Dict[str, FieldState] = {}
    for name, val in initial.items():
        state[name] = FieldState(value=Signal(val), error=Signal(None), touched=Signal(False))
    return state


# ----------------- Binding helpers -----------------


def bind_text(field: FieldState, *, validators: Optional[List[Validator]] = None) -> Dict[str, Any]:
    """Bind a text input to a field with validation on every `input` event.

    Args:
        field: Target [`FieldState`][wybthon.FieldState].
        validators: Optional list of validators. When provided, the
            field's `error` signal is updated on every keystroke.

    Returns:
        Props dict suitable for spreading onto a text input
        (`value` + `on_input`).
    """
    validators = validators or []

    def on_input(evt) -> None:  # DomEvent
        val = evt.target.value if evt.target is not None else ""
        if val is None:
            val = ""
        field.value.set(val)
        field.touched.set(True)
        field.error.set(validate(val, validators))

    return {
        "value": field.value.get(),
        "on_input": on_input,
    }


def bind_checkbox(field: FieldState) -> Dict[str, Any]:
    """Bind a checkbox input to a boolean field.

    Args:
        field: Target [`FieldState`][wybthon.FieldState] (treated as
            holding a `bool`).

    Returns:
        Props dict suitable for spreading onto a checkbox
        (`checked` + `on_change`).
    """

    def on_change(evt) -> None:  # DomEvent
        checked = bool(evt.target.checked) if evt.target is not None else False
        field.value.set(checked)
        field.touched.set(True)
        field.error.set(None)

    return {
        "checked": bool(field.value.get()),
        "on_change": on_change,
    }


def bind_select(field: FieldState) -> Dict[str, Any]:
    """Bind a `<select>` element to a field, updating value on `change`.

    Args:
        field: Target [`FieldState`][wybthon.FieldState].

    Returns:
        Props dict suitable for spreading onto a `<select>` element
        (`value` + `on_change`).
    """

    def on_change(evt) -> None:  # DomEvent
        val = evt.target.value if evt.target is not None else ""
        if val is None:
            val = ""
        field.value.set(val)
        field.touched.set(True)
        field.error.set(None)

    return {
        "value": field.value.get(),
        "on_change": on_change,
    }


def on_submit(handler: Callable[[Dict[str, FieldState]], Any], form: Dict[str, FieldState]) -> Callable[[Any], Any]:
    """Create a submit handler that prevents default and forwards to `handler`.

    Args:
        handler: Callback invoked with the form state when submit
            fires.
        form: Form state map produced by
            [`form_state`][wybthon.form_state].

    Returns:
        An event handler suitable for `on_submit=` on a `<form>`.
    """

    def _onsubmit(evt) -> None:
        try:
            evt.prevent_default()
        except Exception:
            pass
        handler(form)

    return _onsubmit


# ----------------- Aggregated validation and a11y helpers -----------------


def validate_field(field: FieldState, validators: Optional[List[Validator]] = None) -> Optional[str]:
    """Validate a single field and update its `error` and `touched` signals.

    Args:
        field: Target [`FieldState`][wybthon.FieldState].
        validators: Validators to apply. When omitted or empty, the
            field is treated as valid.

    Returns:
        The first error message produced by the validators, or `None`
        when the field is valid.
    """
    rules: List[Validator] = validators or []
    try:
        value = field.value.get()
    except Exception:
        value = None
    error_msg = validate(value, rules) if rules else None
    try:
        field.touched.set(True)
        field.error.set(error_msg)
    except Exception:
        pass
    return error_msg


def validate_form(
    form: Dict[str, FieldState], rules: Dict[str, List[Validator]]
) -> Tuple[bool, Dict[str, Optional[str]]]:
    """Validate every field in a form against a rules map.

    Mutates each field's `touched` and `error` signals as a side
    effect.

    Args:
        form: Form state map (typically produced by
            [`form_state`][wybthon.form_state]).
        rules: Mapping from field name to a list of validators.
            Unknown field names are ignored.

    Returns:
        A `(is_valid, errors)` tuple where `is_valid` is `True` only
        when every validator passes and `errors` maps each field name
        to its current error message (or `None`).
    """
    errors: Dict[str, Optional[str]] = {}
    all_valid = True
    for name, validators in rules.items():
        field = form.get(name)
        if field is None:
            errors[name] = None
            continue
        err = validate_field(field, validators or [])
        errors[name] = err
        if err is not None:
            all_valid = False
    return all_valid, errors


def on_submit_validated(
    rules: Dict[str, List[Validator]],
    handler: Callable[[Dict[str, FieldState]], Any],
    form: Dict[str, FieldState],
) -> Callable[[Any], Any]:
    """Submit handler that validates the whole form before calling `handler`.

    Prevents the default submit action, validates via
    [`validate_form`][wybthon.validate_form], and invokes `handler`
    only when validation passes.

    Args:
        rules: Mapping from field name to a list of validators.
        handler: Callback invoked with the form state on success.
        form: Form state map produced by
            [`form_state`][wybthon.form_state].

    Returns:
        An event handler suitable for `on_submit=` on a `<form>`.
    """

    def _onsubmit(evt) -> None:
        try:
            evt.prevent_default()
        except Exception:
            pass
        is_valid, _ = validate_form(form, rules)
        if is_valid:
            handler(form)

    return _onsubmit


def rules_from_schema(schema: Dict[str, Dict[str, Any]]) -> Dict[str, List[Validator]]:
    """Build a validators map from a small declarative schema.

    Supported per-field keys:

    - `required`: `bool` or `str` (if a string, it is used as the
      custom message).
    - `min_length`: `int`. Optional custom message via
      `min_length_message`.
    - `max_length`: `int`. Optional custom message via
      `max_length_message`.
    - `email`: `bool` or `str` (if a string, it is used as the
      custom message).

    Args:
        schema: Mapping from field name to its rule spec dict.

    Returns:
        A validators map suitable for
        [`validate_form`][wybthon.validate_form].

    Example:
        ```python
        rules_from_schema({
            "name": {"required": True, "min_length": 2},
            "email": {"email": True},
        })
        ```
    """
    rules: Dict[str, List[Validator]] = {}
    for field_name, spec in schema.items():
        vlist: List[Validator] = []

        req = spec.get("required")
        if req:
            msg = req if isinstance(req, str) else "This field is required"
            vlist.append(required(msg))

        if "min_length" in spec and spec.get("min_length") is not None:
            try:
                n = int(spec.get("min_length"))
            except Exception:
                n = 0
            vlist.append(min_length(n, spec.get("min_length_message")))

        if "max_length" in spec and spec.get("max_length") is not None:
            try:
                n2 = int(spec.get("max_length"))
            except Exception:
                n2 = 0
            vlist.append(max_length(n2, spec.get("max_length_message")))

        em = spec.get("email")
        if em:
            msg2 = em if isinstance(em, str) else "Invalid email address"
            vlist.append(email(msg2))

        rules[field_name] = vlist

    return rules


def a11y_control_attrs(field: FieldState, *, described_by_id: Optional[str] = None) -> Dict[str, Any]:
    """Return ARIA attributes for an input or select control bound to a field.

    - `aria-invalid` is set to `"true"` when the field currently has
      an error, otherwise `"false"`.
    - `aria-describedby` references `described_by_id` when an error
      is present, allowing screen readers to announce the message.

    Args:
        field: Bound [`FieldState`][wybthon.FieldState].
        described_by_id: Optional id of the element rendered by
            [`error_message_attrs`][wybthon.error_message_attrs].

    Returns:
        Props dict to spread onto the control.
    """
    try:
        has_error = field.error.get() is not None
    except Exception:
        has_error = False
    attrs: Dict[str, Any] = {"aria-invalid": "true" if has_error else "false"}
    if described_by_id and has_error:
        attrs["aria-describedby"] = described_by_id
    return attrs


def error_message_attrs(*, id: str) -> Dict[str, Any]:
    """Return attributes for an accessible error-message container.

    The container becomes a polite live region so that updates are
    announced to assistive technology without interrupting the user.

    Args:
        id: DOM id to assign to the error container. Pair with
            [`a11y_control_attrs`][wybthon.a11y_control_attrs] so the
            input references this element via `aria-describedby`.

    Returns:
        Props dict to spread onto the error container element.
    """
    return {"id": id, "role": "alert", "aria-live": "polite"}
