"""Components: reactive props (no remount), forward_ref, children, lifecycle."""

from app.testkit import tid

from wybthon import (
    Ref,
    Show,
    button,
    component,
    create_signal,
    div,
    dynamic,
    forward_ref,
    h,
    h2,
    input_,
    on_cleanup,
    on_mount,
    p,
    span,
    untrack,
)


@component
def Page():
    label, set_label = create_signal("hello")
    display_mounts, set_display_mounts = create_signal(0)

    @component
    def Display(text=""):
        on_mount(lambda: set_display_mounts(untrack(display_mounts) + 1))
        return span(dynamic(lambda: str(text())), **tid("comp-display"))

    input_ref = Ref()
    ref_attached, set_ref_attached = create_signal(False)
    Fancy = forward_ref(lambda props, ref: input_(type="text", ref=ref, **tid("comp-ref-input")))
    on_mount(lambda: set_ref_attached(input_ref.current is not None))

    @component
    def Card(children=None):
        kids = untrack(children) if callable(children) else children
        if kids is None:
            kids = []
        if not isinstance(kids, list):
            kids = [kids]
        return div(span("card:", **tid("comp-card-label")), *kids, **tid("comp-card"))

    shown, set_shown = create_signal(True)
    life_mounts, set_life_mounts = create_signal(0)
    life_cleanups, set_life_cleanups = create_signal(0)

    @component
    def Lifecycle():
        on_mount(lambda: set_life_mounts(untrack(life_mounts) + 1))
        on_cleanup(lambda: set_life_cleanups(untrack(life_cleanups) + 1))
        return span("alive", **tid("comp-life"))

    return div(
        h2("Components"),
        div(
            h(Display, {"text": label}),
            span(display_mounts, **tid("comp-display-mounts")),
            button("change label", on_click=lambda e: set_label("world"), **tid("comp-label-btn")),
        ),
        div(
            h(Fancy, {"ref": input_ref}),
            span(dynamic(lambda: "yes" if ref_attached() else "no"), **tid("comp-ref-attached")),
        ),
        div(h(Card, {}, span("inside", **tid("comp-card-child")))),
        div(
            button("toggle life", on_click=lambda e: set_shown(not shown()), **tid("comp-life-toggle")),
            Show(when=shown, children=lambda: h(Lifecycle, {})),
            p(
                "mounts: ",
                span(life_mounts, **tid("comp-life-mounts")),
                " cleanups: ",
                span(life_cleanups, **tid("comp-life-cleanups")),
            ),
        ),
        **tid("page-components"),
    )
