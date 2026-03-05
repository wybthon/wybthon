from wybthon import ErrorBoundary, button, div, h, p, signal


def Page(_props):
    def Bug(_props):
        raise RuntimeError("Boom")

    key_sig = signal(0)

    def Fallback(err, reset):
        return div(
            p(f"Caught error: {err}"),
            button("Try again", on_click=lambda e: reset()),
            style={"color": "crimson"},
        )

    def bump_key(_evt):
        key_sig.set(key_sig.get() + 1)

    return div(
        h("h3", {}, "Error Boundary Demo"),
        h(
            ErrorBoundary,
            {"fallback": Fallback},
            div(p("This component will throw:"), h(Bug, {})),
        ),
        h(
            ErrorBoundary,
            {"fallback": Fallback, "reset_key": lambda: key_sig.get()},
            div(p("This one resets via key change:"), h(Bug, {})),
        ),
        button("Change reset_key", on_click=bump_key),
    )
