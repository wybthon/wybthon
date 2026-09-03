"""Reactivity primitives surfaced to the DOM: signal, memo, effect, automatic batching, untrack."""

from app.testkit import tid

from wybthon import (
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
def Page(**rest):
    count, set_count = create_signal(0)
    doubled = create_memo(lambda: count() * 2)

    effect_runs, set_effect_runs = create_signal(0)

    # Split form: the compute stage tracks `count`; the apply stage may write.
    create_effect(count, lambda _value: set_effect_runs(lambda n: n + 1))

    def do_double_write(_e):
        # Two writes in one handler batch automatically: effects run once.
        set_count(lambda n: n + 1)
        set_count(lambda n: n + 1)

    a, set_a = create_signal(0)
    b, set_b = create_signal(0)
    untracked_runs, set_untracked_runs = create_signal(0)

    def track_a_only():
        a()  # tracked dependency
        return untrack(b)  # read without subscribing

    create_effect(track_a_only, lambda _value: set_untracked_runs(lambda n: n + 1))

    return div(
        h2("Reactivity"),
        div(
            p("count: ", span(count, **tid("rx-count"))),
            p("doubled: ", span(doubled, **tid("rx-doubled"))),
            button("+1", on_click=lambda e: set_count(lambda n: n + 1), **tid("rx-inc")),
            button("reset", on_click=lambda e: set_count(0), **tid("rx-reset")),
            button("batch +2", on_click=do_double_write, **tid("rx-batch")),
            p("effect runs: ", span(effect_runs, **tid("rx-effect-runs"))),
        ),
        div(
            p("untracked effect runs: ", span(untracked_runs, **tid("rx-untracked-runs"))),
            button("set a (tracked)", on_click=lambda e: set_a(lambda n: n + 1), **tid("rx-set-a")),
            button("set b (untracked)", on_click=lambda e: set_b(lambda n: n + 1), **tid("rx-set-b")),
        ),
        **tid("page-reactivity"),
    )
