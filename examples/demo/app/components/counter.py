from wybthon import button, component, create_signal, div, on_mount, p, span, untrack


@component
def Counter(initial=0):
    """Setup-once counter using a reactive hole.

    The component body runs **once**.  ``initial`` is a *reactive
    accessor* in the new fully-reactive props model, so we wrap the
    initial read in :func:`untrack` to capture the seed value without
    subscribing.  ``count`` -- the zero-arg getter returned by
    :func:`create_signal` -- is then passed directly into the tree as
    a reactive hole, so the only DOM update on click is the single
    text node.
    """
    count, set_count = create_signal(untrack(initial))

    on_mount(lambda: print("Counter mounted with initial count:", count()))

    return div(
        p("Count: ", span(count)),
        button("Increment", on_click=lambda e: set_count(count() + 1)),
        class_="counter",
    )
