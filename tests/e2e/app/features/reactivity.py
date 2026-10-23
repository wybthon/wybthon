"""Reactivity primitives surfaced to the DOM: signal, memo, effect, automatic batching, untrack."""

from wybthon import component, create_effect, create_memo, create_signal, html, untrack


@component
def Page():
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

    # `{count}` passes the signal itself (a name); `{doubled()}` and
    # `{count() * 2 + 1}` are compiled into getters.
    return html(t"""
      <div data-testid="page-reactivity">
        <h2>Reactivity</h2>
        <div>
          <p>count: <span data-testid="rx-count">{count}</span></p>
          <p>doubled: <span data-testid="rx-doubled">{doubled()}</span></p>
          <p>inline: <span data-testid="rx-inline">{count() * 2 + 1}</span></p>
          <button data-testid="rx-inc" onclick={(lambda e: set_count(lambda n: n + 1))}>+1</button>
          <button data-testid="rx-reset" onclick={(lambda e: set_count(0))}>reset</button>
          <button data-testid="rx-batch" onclick={do_double_write}>batch +2</button>
          <p>effect runs: <span data-testid="rx-effect-runs">{effect_runs()}</span></p>
        </div>
        <div>
          <p>untracked effect runs: <span data-testid="rx-untracked-runs">{untracked_runs()}</span></p>
          <button data-testid="rx-set-a" onclick={(lambda e: set_a(lambda n: n + 1))}>set a (tracked)</button>
          <button data-testid="rx-set-b" onclick={(lambda e: set_b(lambda n: n + 1))}>set b (untracked)</button>
        </div>
      </div>
    """)
