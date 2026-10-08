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


def test_warn_once_dedupes_per_category_and_key(capsys):
    from wybthon._warnings import _reset_warning_dedupe, warn_once

    _reset_warning_dedupe()
    try:
        warn_once("cat", 1, "first")
        warn_once("cat", 1, "first again")
        warn_once("cat", 2, "second")
        warn_once("other", 1, "third")
        err = capsys.readouterr().err
        assert err.count("[wybthon] Warning:") == 3
        assert "first again" not in err
    finally:
        _reset_warning_dedupe()


def test_dev_mode_constant_is_not_exported_at_top_level():
    import wybthon

    assert not hasattr(wybthon, "DEV_MODE")
    assert wybthon.is_dev_mode is is_dev_mode
    assert wybthon.set_dev_mode is set_dev_mode


def test_component_name_of_decorated_component():
    from wybthon import component

    @component
    def Greeting():
        return None

    assert component_name(Greeting) == "Greeting"


def test_prop_checks_follow_dev_mode():
    import pytest

    from wybthon import Prop, Props, component

    class CardProps(Props):
        title: Prop[str]

    @component
    def Card(props: CardProps):
        return None

    @component
    def Bare():
        return None

    with pytest.raises(TypeError):
        Card(bogus=1)
    with pytest.raises(TypeError):
        Card()
    with pytest.raises(TypeError):
        Bare(title="x")
    original = is_dev_mode()
    try:
        set_dev_mode(False)
        assert Card(bogus=1).props == {"bogus": 1}
        Bare(title="x")
    finally:
        set_dev_mode(original)
