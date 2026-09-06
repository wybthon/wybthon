"""Components: reactive props (no remount), refs, children, lifecycle."""

from app.testkit import tid

from wybthon import (
    Prop,
    Ref,
    Show,
    button,
    component,
    create_signal,
    div,
    h2,
    input_,
    on_cleanup,
    on_settled,
    p,
    prop,
    span,
)


@component
def Page(**rest):
    label, set_label = create_signal("hello")
    display_mounts, set_display_mounts = create_signal(0)

    @component
    def Display(text: Prop[str] = prop("")):
        on_settled(lambda: set_display_mounts(lambda n: n + 1))
        return span(lambda: str(text()), **tid("comp-display"))

    input_ref = Ref()
    ref_attached, set_ref_attached = create_signal(False)

    @component
    def Fancy(ref: Prop = prop(None)):
        # Refs pass through like any other prop; no forward_ref needed.
        return input_(type="text", ref=ref.peek(), **tid("comp-ref-input"))

    on_settled(lambda: set_ref_attached(input_ref.current is not None))

    @component
    def Card(children: Prop = prop(None)):
        return div(span("card:", **tid("comp-card-label")), children, **tid("comp-card"))

    shown, set_shown = create_signal(True)
    life_mounts, set_life_mounts = create_signal(0)
    life_cleanups, set_life_cleanups = create_signal(0)

    @component
    def Lifecycle():
        on_settled(lambda: set_life_mounts(lambda n: n + 1))
        on_cleanup(lambda: set_life_cleanups(lambda n: n + 1))
        return span("alive", **tid("comp-life"))

    return div(
        h2("Components"),
        div(
            Display(text=label),
            span(display_mounts, **tid("comp-display-mounts")),
            button("change label", on_click=lambda e: set_label("world"), **tid("comp-label-btn")),
        ),
        div(
            Fancy(ref=input_ref),
            span(lambda: "yes" if ref_attached() else "no", **tid("comp-ref-attached")),
        ),
        div(Card(span("inside", **tid("comp-card-child")))),
        div(
            button("toggle life", on_click=lambda e: set_shown(lambda v: not v), **tid("comp-life-toggle")),
            Show(shown, lambda: Lifecycle()),
            p(
                "mounts: ",
                span(life_mounts, **tid("comp-life-mounts")),
                " cleanups: ",
                span(life_cleanups, **tid("comp-life-cleanups")),
            ),
        ),
        **tid("page-components"),
    )
