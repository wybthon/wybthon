from wybthon import (
    For,
    button,
    component,
    create_memo,
    create_signal,
    div,
    dynamic,
    li,
    p,
    ul,
)


@component
def NamesList():
    """Curated names list using a reactive ``For`` for fine-grained list updates."""
    names, set_names = create_signal([])
    starts_with_a = create_memo(lambda: len([n for n in names() if str(n).lower().startswith("a")]))

    def add_name(name):
        return lambda _evt: set_names(names() + [name])

    def clear(_evt):
        set_names([])

    return div(
        p(dynamic(lambda: f"Total: {len(names())} | Starts with A: {starts_with_a()}")),
        div(
            button("+ Ada", on_click=add_name("Ada")),
            button("+ Alan", on_click=add_name("Alan")),
            button("Clear", on_click=clear),
        ),
        ul(For(each=names, children=lambda n, _i: li(n))),
    )
