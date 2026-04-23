from wybthon import ErrorBoundary, button, code, component, create_signal, div, h, h2, h3, p, pre


@component
def Page():
    @component
    def Bug():
        raise RuntimeError("Boom!")

    key_val, set_key_val = create_signal(0)

    def Fallback(err, reset):
        return div(
            p(f"Caught: {err}"),
            button("Try Again", on_click=lambda e: reset()),
            style={"color": "var(--error)", "padding": "0.5rem 0"},
        )

    def bump_key(_evt):
        set_key_val(key_val() + 1)

    return div(
        div(
            h2("Error Boundaries"),
            p("Graceful error handling with fallback UI and recovery."),
            class_="page-header",
        ),
        div(
            h3("Automatic Error Catching"),
            p("The component below throws a RuntimeError. The ErrorBoundary catches it:"),
            h(ErrorBoundary, {"fallback": Fallback}, div(h(Bug, {}))),
            class_="demo-section",
        ),
        div(
            h3("Reset via Key Change"),
            p("This boundary re-renders its children when the reset key changes:"),
            h(ErrorBoundary, {"fallback": Fallback, "reset_key": key_val}, div(h(Bug, {}))),
            button("Change Reset Key", on_click=bump_key),
            class_="demo-section",
        ),
        div(
            h3("How It Works"),
            pre(
                code(
                    "def Fallback(err, reset):\n"
                    "    ...\n"
                    'h(ErrorBoundary, {"fallback": Fallback,\n'
                    '    "reset_key": key_val}, children)'
                ),
                class_="code-block",
            ),
            class_="demo-section",
        ),
        class_="page",
    )
