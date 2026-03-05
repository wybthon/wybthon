from wybthon import h, use_effect, use_state


def Counter(props):
    count, set_count = use_state(0)

    def on_mount():
        print("Counter mounted with initial count:", count)

    use_effect(on_mount, [])

    return h(
        "div",
        {"class": "counter"},
        h("p", {}, f"Count: {count}"),
        h("button", {"on_click": lambda e: set_count(lambda c: c + 1)}, "Increment"),
    )
