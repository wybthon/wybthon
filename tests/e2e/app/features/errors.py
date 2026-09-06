"""Errored: catch a child render error, show fallback, and reset to recover."""

from app.testkit import tid

from wybthon import Errored, button, component, create_signal, div, h2, span


@component
def Page(**rest):
    should_throw, set_should_throw = create_signal(True)
    reset_key, set_reset_key = create_signal(0)

    @component
    def Bug():
        # A one-time read: the boundary remounts this component on reset.
        if should_throw.peek():
            raise RuntimeError("boom")
        return span("recovered", **tid("err-ok"))

    def fallback(err, reset):
        return div(
            span(f"caught: {err}", **tid("err-fallback")),
            button("retry", on_click=lambda e: reset(), **tid("err-retry")),
        )

    def fix_and_reset(_e):
        set_should_throw(False)
        set_reset_key(lambda n: n + 1)

    return div(
        h2("Errors"),
        Errored(lambda: div(Bug()), fallback=fallback, reset_on=reset_key),
        button("fix + reset", on_click=fix_and_reset, **tid("err-fix")),
        **tid("page-errors"),
    )
