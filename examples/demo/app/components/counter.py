from wybthon import button, component, div, p, use_effect, use_state


@component
def Counter(initial: int = 0):
    count, set_count = use_state(initial)

    def on_mount():
        print("Counter mounted with initial count:", count)

    use_effect(on_mount, [])

    return div(
        p(f"Count: {count}"),
        button("Increment", on_click=lambda e: set_count(lambda c: c + 1)),
        class_name="counter",
    )
