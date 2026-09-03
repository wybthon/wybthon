"""Portal: render children into a different DOM container while staying reactive."""

from app.testkit import tid

from wybthon import Portal, Show, button, component, create_signal, div, h2, span


@component
def Page(**rest):
    show, set_show = create_signal(False)
    count, set_count = create_signal(0)

    def content():
        return div(
            span(lambda: str(count()), **tid("portal-count")),
            **tid("portal-content"),
        )

    return div(
        h2("Portal"),
        button("toggle", on_click=lambda e: set_show(lambda v: not v), **tid("portal-toggle")),
        button("inc", on_click=lambda e: set_count(lambda n: n + 1), **tid("portal-inc")),
        div(
            Show(show, lambda: Portal(content(), mount="#portal-target-inner")),
            **tid("portal-source"),
        ),
        div(div(id="portal-target-inner", **tid("portal-target-inner")), **tid("portal-target")),
        **tid("page-portal"),
    )
