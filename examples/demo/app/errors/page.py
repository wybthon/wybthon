from wybthon import ErrorBoundary, button, code, component, div, h, h2, h3, p, pre, signal


@component
def Page():
    def Bug(_props):
        raise RuntimeError("Boom!")

    key_sig = signal(0)

    def Fallback(err, reset):
        return div(
            p(f"Caught: {err}"),
            button("Try Again", on_click=lambda e: reset()),
            style={"color": "var(--error)", "padding": "0.5rem 0"},
        )

    def bump_key(_evt):
        key_sig.set(key_sig.get() + 1)

    return div(
        div(
            h2("Error Boundaries"),
            p("Graceful error handling with fallback UI and recovery."),
            class_name="page-header",
        ),
        div(
            h3("Automatic Error Catching"),
            p("The component below throws a RuntimeError. The ErrorBoundary catches it:"),
            h(
                ErrorBoundary,
                {"fallback": Fallback},
                div(h(Bug, {})),
            ),
            class_name="demo-section",
        ),
        div(
            h3("Reset via Key Change"),
            p("This boundary re-renders its children when the reset key changes:"),
            h(
                ErrorBoundary,
                {"fallback": Fallback, "reset_key": lambda: key_sig.get()},
                div(h(Bug, {})),
            ),
            button("Change Reset Key", on_click=bump_key),
            class_name="demo-section",
        ),
        div(
            h3("How It Works"),
            pre(
                code(
                    "def Fallback(err, reset):\n"
                    '    return div(p(f"Caught: {err}"),\n'
                    '              button("Retry", on_click=lambda e: reset()))\n'
                    "\n"
                    "h(ErrorBoundary, {\n"
                    '    "fallback": Fallback,\n'
                    '    "reset_key": lambda: key_sig.get(),\n'
                    "}, children)"
                ),
                class_name="code-block",
            ),
            class_name="demo-section",
        ),
        class_name="page",
    )
