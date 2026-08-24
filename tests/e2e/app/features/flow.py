"""Flow control: Show, For (keyed and index modes), Repeat, Switch/Match, and Dynamic."""

from app.testkit import tid

from wybthon import (
    Dynamic,
    For,
    Match,
    Repeat,
    Show,
    Switch,
    button,
    component,
    create_signal,
    div,
    dynamic,
    h2,
    li,
    span,
    ul,
)

_NEXT_STATUS = {"idle": "loading", "loading": "ready", "ready": "idle"}
_NEXT_TAG = {"h3": "h2", "h2": "p", "p": "h3"}


@component
def Page():
    visible, set_visible = create_signal(True)

    items, set_items = create_signal(["alpha", "beta", "gamma"])
    next_id = [1]

    def add(_e):
        set_items([*items(), f"item-{next_id[0]}"])
        next_id[0] += 1

    def remove_last(_e):
        cur = items()
        if cur:
            set_items(cur[:-1])

    def reverse(_e):
        set_items(list(reversed(items())))

    stars, set_stars = create_signal(3)
    status, set_status = create_signal("idle")
    tag, set_tag = create_signal("h3")

    return div(
        h2("Flow"),
        div(
            button("toggle", on_click=lambda e: set_visible(not visible()), **tid("flow-show-toggle")),
            Show(
                when=visible,
                children=lambda: span("shown", **tid("flow-show-on")),
                fallback=lambda: span("hidden", **tid("flow-show-off")),
            ),
        ),
        div(
            button("add", on_click=add, **tid("flow-for-add")),
            button("remove", on_click=remove_last, **tid("flow-for-remove")),
            button("reverse", on_click=reverse, **tid("flow-for-reverse")),
            span(dynamic(lambda: str(len(items()))), **tid("flow-for-count")),
            ul(
                For(
                    each=items,
                    children=lambda item, idx: li(dynamic(lambda: f"{idx()}:{item()}"), key=item()),
                ),
                **tid("flow-for-list"),
            ),
            ul(
                For(
                    each=items,
                    key="index",
                    children=lambda item, index: li(dynamic(lambda: f"[{index()}]{item()}")),
                ),
                **tid("flow-index-list"),
            ),
        ),
        div(
            button("star +", on_click=lambda e: set_stars(stars() + 1), **tid("flow-repeat-inc")),
            button("star -", on_click=lambda e: set_stars(max(0, stars() - 1)), **tid("flow-repeat-dec")),
            ul(
                Repeat(
                    times=stars,
                    children=lambda i: li(f"star-{i}"),
                    fallback=lambda: li("no stars"),
                ),
                **tid("flow-repeat-list"),
            ),
        ),
        div(
            button("cycle status", on_click=lambda e: set_status(_NEXT_STATUS[status()]), **tid("flow-switch-cycle")),
            Switch(
                Match(when=lambda: status() == "loading", children=lambda: span("loading", **tid("flow-switch-out"))),
                Match(when=lambda: status() == "ready", children=lambda: span("ready", **tid("flow-switch-out"))),
                fallback=lambda: span("idle", **tid("flow-switch-out")),
            ),
        ),
        div(
            button("cycle tag", on_click=lambda e: set_tag(_NEXT_TAG[tag()]), **tid("flow-dyn-cycle")),
            Dynamic(component=lambda: tag(), children=["dyn"], **tid("flow-dyn-out")),
        ),
        **tid("page-flow"),
    )
