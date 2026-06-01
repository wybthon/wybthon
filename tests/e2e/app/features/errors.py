"""ErrorBoundary: catch a child render error, show fallback, and reset to recover."""

from app.testkit import tid

from wybthon import ErrorBoundary, button, component, create_signal, div, dynamic, h, h2, span


@component
def Page():
    should_throw, set_should_throw = create_signal(True)
    reset_key, set_reset_key = create_signal(0)

    @component
    def Bug():
        if should_throw():
            raise RuntimeError("boom")
        return span("recovered", **tid("err-ok"))

    def fallback(err, reset):
        return div(
            span(dynamic(lambda: f"caught: {err}"), **tid("err-fallback")),
            button("retry", on_click=lambda e: reset(), **tid("err-retry")),
        )

    def fix_and_reset(_e):
        set_should_throw(False)
        set_reset_key(reset_key() + 1)

    return div(
        h2("Errors"),
        h(ErrorBoundary, {"fallback": fallback, "reset_key": reset_key}, div(h(Bug, {}))),
        button("fix + reset", on_click=fix_and_reset, **tid("err-fix")),
        **tid("page-errors"),
    )
