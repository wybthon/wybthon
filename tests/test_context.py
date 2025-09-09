from wybthon.context import create_context, use_context, push_provider_value, pop_provider_value


def test_context_stack_basic():
    Theme = create_context("light")
    assert use_context(Theme) == "light"

    push_provider_value(Theme, "dark")
    try:
        assert use_context(Theme) == "dark"
        push_provider_value(Theme, "contrast")
        try:
            assert use_context(Theme) == "contrast"
        finally:
            pop_provider_value()
        assert use_context(Theme) == "dark"
    finally:
        pop_provider_value()
    assert use_context(Theme) == "light"


