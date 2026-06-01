"""Reactivity primitives surfaced to the DOM: signal, memo, effect, batch, untrack."""

from app.testkit import tid

from wybthon import (
    batch,
    button,
    component,
    create_effect,
    create_memo,
    create_signal,
    div,
    h2,
    p,
    span,
    untrack,
)


@component
def Page():
    count, set_count = create_signal(0)
    doubled = create_memo(lambda: count() * 2)

    effect_runs, set_effect_runs = create_signal(0)

    def track_count():
        count()  # establish dependency
        set_effect_runs(untrack(effect_runs) + 1)

    create_effect(track_count)

    def do_batch(_e):
        with batch():
            set_count(count() + 1)
            set_count(count() + 1)

    a, set_a = create_signal(0)
    b, set_b = create_signal(0)
    untracked_runs, set_untracked_runs = create_signal(0)

    def track_a_only():
        a()  # tracked dependency
        untrack(b)  # read without subscribing
        set_untracked_runs(untrack(untracked_runs) + 1)

    create_effect(track_a_only)

    return div(
        h2("Reactivity"),
        div(
            p("count: ", span(count, **tid("rx-count"))),
            p("doubled: ", span(doubled, **tid("rx-doubled"))),
            button("+1", on_click=lambda e: set_count(count() + 1), **tid("rx-inc")),
            button("reset", on_click=lambda e: set_count(0), **tid("rx-reset")),
            button("batch +2", on_click=do_batch, **tid("rx-batch")),
            p("effect runs: ", span(effect_runs, **tid("rx-effect-runs"))),
        ),
        div(
            p("untracked effect runs: ", span(untracked_runs, **tid("rx-untracked-runs"))),
            button("set a (tracked)", on_click=lambda e: set_a(a() + 1), **tid("rx-set-a")),
            button("set b (untracked)", on_click=lambda e: set_b(b() + 1), **tid("rx-set-b")),
        ),
        **tid("page-reactivity"),
    )
