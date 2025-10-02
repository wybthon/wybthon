from wybthon.context import create_context, pop_provider_value, push_provider_value, use_context


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
