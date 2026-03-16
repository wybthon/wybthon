from wybthon import button, component, create_signal, div, on_mount, p


@component
def Counter(initial=0):
    count, set_count = create_signal(initial())

    on_mount(lambda: print("Counter mounted with initial count:", count()))

    def render():
        return div(
            p(f"Count: {count()}"),
            button("Increment", on_click=lambda e: set_count(count() + 1)),
            class_name="counter",
        )

    return render
