from wybthon import button, component, create_signal, div, on_mount, p, span


@component
def Counter(initial=0):
    """Setup-once counter using a reactive hole.

    The component body runs **once**.  ``count`` (the zero-arg getter
    returned by ``create_signal``) is wrapped automatically as a
    reactive hole, so when the signal changes the only DOM update is
    the single text node.
    """
    count, set_count = create_signal(initial)

    on_mount(lambda: print("Counter mounted with initial count:", count()))

    return div(
        p("Count: ", span(count)),
        button("Increment", on_click=lambda e: set_count(count() + 1)),
        class_name="counter",
    )
