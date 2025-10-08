from wybthon import ErrorBoundary, h, signal


def Page(_props):
    def Bug(_props):
        raise RuntimeError("Boom")

    # showcase both imperative reset and key-based reset
    key_sig = signal(0)

    def Fallback(err, reset):
        return h(
            "div",
            {"style": {"color": "crimson"}},
            h("p", {}, f"Caught error: {err}"),
            h("button", {"on_click": lambda e: reset()}, "Try again"),
        )

    def bump_key(_evt):
        key_sig.set(key_sig.get() + 1)

    return h(
        "div",
        {},
        h("h3", {}, "Error Boundary Demo"),
        h(
            ErrorBoundary,
            {"fallback": Fallback},
            h("div", {}, h("p", {}, "This component will throw:"), h(Bug, {})),
        ),
        h(
            ErrorBoundary,
            {"fallback": Fallback, "reset_key": lambda: key_sig.get()},
            h("div", {}, h("p", {}, "This one resets via key change:"), h(Bug, {})),
        ),
        h("button", {"on_click": bump_key}, "Change reset_key"),
    )
