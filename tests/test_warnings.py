"""Tests for the _warnings module."""

from wybthon._warnings import (
    component_name,
    is_dev_mode,
    log_error,
    set_dev_mode,
    warn,
)


def test_dev_mode_default():
    assert is_dev_mode() is True


def test_set_dev_mode():
    original = is_dev_mode()
    try:
        set_dev_mode(False)
        assert is_dev_mode() is False
        set_dev_mode(True)
        assert is_dev_mode() is True
    finally:
        set_dev_mode(original)


def test_warn_outputs_to_stderr(capsys):
    warn("test warning")
    captured = capsys.readouterr()
    assert "[wybthon] Warning: test warning" in captured.err


def test_warn_silent_when_dev_mode_off(capsys):
    original = is_dev_mode()
    try:
        set_dev_mode(False)
        warn("should not appear")
        captured = capsys.readouterr()
        assert captured.err == ""
    finally:
        set_dev_mode(original)


def test_log_error_outputs_to_stderr(capsys):
    log_error("something broke")
    captured = capsys.readouterr()
    assert "[wybthon] Error: something broke" in captured.err


def test_log_error_with_exception(capsys):
    try:
        raise ValueError("bad value")
    except ValueError as e:
        log_error("caught error", e)
    captured = capsys.readouterr()
    assert "[wybthon] Error: caught error" in captured.err
    assert "ValueError" in captured.err
    assert "bad value" in captured.err


def test_log_error_no_traceback_when_dev_off(capsys):
    original = is_dev_mode()
    try:
        set_dev_mode(False)
        try:
            raise ValueError("hidden")
        except ValueError as e:
            log_error("caught", e)
        captured = capsys.readouterr()
        assert "[wybthon] Error: caught" in captured.err
        assert "hidden" not in captured.err
    finally:
        set_dev_mode(original)


def test_component_name_string():
    assert component_name("div") == "<div>"


def test_component_name_function():
    def MyComponent():
        pass

    assert component_name(MyComponent) == "MyComponent"


def test_component_name_class():
    class Widget:
        pass

    assert component_name(Widget) == "Widget"


def test_component_name_instance():
    class Widget:
        pass

    assert component_name(Widget()) == "Widget"


def test_component_name_fallback():
    result = component_name(42)
    assert "int" in result or "42" in result
