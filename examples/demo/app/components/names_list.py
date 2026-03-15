from wybthon import button, component, create_memo, create_signal, div, li, p, ul


@component
def NamesList():
    names, set_names = create_signal([])
    starts_with_a = create_memo(lambda: len([n for n in names() if str(n).lower().startswith("a")]))

    def add_name(name):
        return lambda _evt: set_names(names() + [name])

    def clear(_evt):
        set_names([])

    def render():
        items = [li(n) for n in names()]
        return div(
            p(f"Total: {len(names())} | Starts with A: {starts_with_a()}"),
            div(
                button("+ Ada", on_click=add_name("Ada")),
                button("+ Alan", on_click=add_name("Alan")),
                button("Clear", on_click=clear),
            ),
            ul(*items),
        )

    return render
