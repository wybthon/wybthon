from wybthon import ErrorBoundary, h


def Page(_props):
    def Bug(_props):
        raise RuntimeError("Boom")

    return h(
        ErrorBoundary,
        {"fallback": lambda err: h("div", {"style": {"color": "crimson"}}, f"Caught error: {err}")},
        h(
            "div",
            {},
            h("p", {}, "This component will throw:"),
            h(Bug, {}),
        ),
    )
