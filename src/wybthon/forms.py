from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from .reactivity import Signal, signal

# ----------------- Validation primitives -----------------

Validator = Callable[[Any], Optional[str]]


def required(message: str = "This field is required") -> Validator:
    def _v(value: Any) -> Optional[str]:
        if value is None:
            return message
        if isinstance(value, str) and value.strip() == "":
            return message
        return None

    return _v


def min_length(n: int, message: Optional[str] = None) -> Validator:
    msg = message or f"Minimum length is {n}"

    def _v(value: Any) -> Optional[str]:
        try:
            return None if (value is not None and len(str(value)) >= n) else msg
        except Exception:
            return msg

    return _v


def max_length(n: int, message: Optional[str] = None) -> Validator:
    msg = message or f"Maximum length is {n}"

    def _v(value: Any) -> Optional[str]:
        try:
            return None if (value is not None and len(str(value)) <= n) else msg
        except Exception:
            return msg

    return _v


def email(message: str = "Invalid email address") -> Validator:
    import re

    pattern = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    def _v(value: Any) -> Optional[str]:
        if value is None or str(value).strip() == "":
            return None
        return None if pattern.match(str(value)) else message

    return _v


def validate(value: Any, validators: List[Validator]) -> Optional[str]:
    for v in validators:
        msg = v(value)
        if msg:
            return msg
    return None


# ----------------- Form state -----------------


@dataclass
class FieldState:
    value: Signal[Any]
    error: Signal[Optional[str]]
    touched: Signal[bool]


def form_state(initial: Dict[str, Any]) -> Dict[str, FieldState]:
    state: Dict[str, FieldState] = {}
    for name, val in initial.items():
        state[name] = FieldState(value=signal(val), error=signal(None), touched=signal(False))
    return state


# ----------------- Binding helpers -----------------


def bind_text(field: FieldState, *, validators: Optional[List[Validator]] = None) -> Dict[str, Any]:
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
    def _onsubmit(evt) -> None:
        try:
            evt.prevent_default()
        except Exception:
            pass
        handler(form)

    return _onsubmit
