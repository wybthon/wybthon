"""Form state, validation helpers, and a11y attribute utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from .reactivity import Signal, signal

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
    """Validate that a value is present and non-empty."""

    def _v(value: Any) -> Optional[str]:
        if value is None:
            return message
        if isinstance(value, str) and value.strip() == "":
            return message
        return None

    return _v


def min_length(n: int, message: Optional[str] = None) -> Validator:
    """Validate that stringified value length is at least `n`."""
    msg = message or f"Minimum length is {n}"

    def _v(value: Any) -> Optional[str]:
        try:
            return None if (value is not None and len(str(value)) >= n) else msg
        except Exception:
            return msg

    return _v


def max_length(n: int, message: Optional[str] = None) -> Validator:
    """Validate that stringified value length is at most `n`."""
    msg = message or f"Maximum length is {n}"

    def _v(value: Any) -> Optional[str]:
        try:
            return None if (value is not None and len(str(value)) <= n) else msg
        except Exception:
            return msg

    return _v


def email(message: str = "Invalid email address") -> Validator:
    """Validate a basic email address format (lightweight regex)."""
    import re

    pattern = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    def _v(value: Any) -> Optional[str]:
        if value is None or str(value).strip() == "":
            return None
        return None if pattern.match(str(value)) else message

    return _v


def validate(value: Any, validators: List[Validator]) -> Optional[str]:
    """Return first validation error or None when all validators pass."""
    for v in validators:
        msg = v(value)
        if msg:
            return msg
    return None


# ----------------- Form state -----------------


@dataclass
class FieldState:
    """Signals representing a field's value, error message, and touched state."""

    value: Signal[Any]
    error: Signal[Optional[str]]
    touched: Signal[bool]


def form_state(initial: Dict[str, Any]) -> Dict[str, FieldState]:
    """Create a form state map from initial values using Signals."""
    state: Dict[str, FieldState] = {}
    for name, val in initial.items():
        state[name] = FieldState(value=signal(val), error=signal(None), touched=signal(False))
    return state


# ----------------- Binding helpers -----------------


def bind_text(field: FieldState, *, validators: Optional[List[Validator]] = None) -> Dict[str, Any]:
    """Bind a text input to a field with validation on input events."""
    validators = validators or []

    def on_input(evt) -> None:  # DomEvent
        try:
            target = evt.target.element
            val = getattr(target, "value", "")
        except Exception:
            val = ""
        field.value.set(val)
        field.touched.set(True)
        field.error.set(validate(val, validators))

    return {
        "value": field.value.get(),
        "on_input": on_input,
    }


def bind_checkbox(field: FieldState) -> Dict[str, Any]:
    """Bind a checkbox input to a boolean field."""

    def on_change(evt) -> None:  # DomEvent
        try:
            target = evt.target.element
            checked = bool(getattr(target, "checked", False))
        except Exception:
            checked = False
        field.value.set(checked)
        field.touched.set(True)
        field.error.set(None)

    return {
        "checked": bool(field.value.get()),
        "on_change": on_change,
    }


def bind_select(field: FieldState) -> Dict[str, Any]:
    """Bind a select element to a field, updating value on change."""

    def on_change(evt) -> None:  # DomEvent
        try:
            target = evt.target.element
            val = getattr(target, "value", "")
        except Exception:
            val = ""
        field.value.set(val)
        field.touched.set(True)
        field.error.set(None)

    return {
        "value": field.value.get(),
        "on_change": on_change,
    }


def on_submit(handler: Callable[[Dict[str, FieldState]], Any], form: Dict[str, FieldState]) -> Callable[[Any], Any]:
    """Create a submit handler that prevents default and calls the handler."""

    def _onsubmit(evt) -> None:
        try:
            evt.prevent_default()
        except Exception:
            pass
        handler(form)

    return _onsubmit


# ----------------- Aggregated validation and a11y helpers -----------------


def validate_field(field: FieldState, validators: Optional[List[Validator]] = None) -> Optional[str]:
    """Validate a single field and update its error/touched signals.

    Returns the error message if any, else None.
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
    """Validate all fields in a form against a rules map.

    Mutates each field's `touched` and `error` signals. Returns (is_valid, errors_map).
    """
    errors: Dict[str, Optional[str]] = {}
    all_valid = True
    for name, validators in rules.items():
        field = form.get(name)
        if field is None:
            # Unknown field in rules – treat as valid but record None
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
    """Submit handler that validates the whole form before invoking handler.

    Prevents the default submit, validates via `validate_form`, and calls `handler(form)`
    only when the form is valid.
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
    """Build a validators map from a simple, lightweight schema.

    Supported keys per field:
    - required: bool or str (if str, used as custom message)
    - min_length: int (optional custom message via min_length_message)
    - max_length: int (optional custom message via max_length_message)
    - email: bool or str (if str, used as custom message)

    Example:
        {
            "name": {"required": True, "min_length": 2},
            "email": {"email": True},
        }
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
    """Return ARIA attributes for an input/select control bound to the field.

    - aria-invalid is set to "true" when there's an error, else "false".
    - aria-describedby includes the provided error element id when an error exists.
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
    """Return attributes for an error message container.

    Use with a live region to announce validation errors to assistive tech.
    """
    return {"id": id, "role": "alert", "aria-live": "polite"}
