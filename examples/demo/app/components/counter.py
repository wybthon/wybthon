from wybthon import button, div, p, use_effect, use_state


def Counter(props):
    count, set_count = use_state(0)

    def on_mount():
        print("Counter mounted with initial count:", count)

    use_effect(on_mount, [])

    return div(
        p(f"Count: {count}"),
        button("Increment", on_click=lambda e: set_count(lambda c: c + 1)),
        class_name="counter",
    )
