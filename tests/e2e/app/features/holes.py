"""Reactive "holes": text holes, derived expressions, node holes, and independence."""

from wybthon import component, create_effect, create_signal, html


@component
def Page():
    count, set_count = create_signal(0)

    first, set_first = create_signal("Ada")
    last, set_last = create_signal("Lovelace")

    mode, set_mode = create_signal("a")

    def node_hole():
        m = mode()
        if m == "a":
            return html(t'<span data-testid="hole-node-inner">alpha</span>')
        if m == "b":
            return html(t'<strong data-testid="hole-node-inner">bravo</strong>')
        return html(t'<em data-testid="hole-node-inner">charlie</em>')

    def next_mode(_e):
        set_mode({"a": "b", "b": "c", "c": "a"}[mode()])

    x, set_x = create_signal(0)
    y, set_y = create_signal(0)
    x_log: list[int] = []
    y_log: list[int] = []
    x_runs, set_x_runs = create_signal(0)
    y_runs, set_y_runs = create_signal(0)

    # Holes may not write signals; they record into plain lists and the
    # counts are published from effects, which run after the holes in the
    # same flush.
    def x_view():
        x_log.append(1)
        return str(x())

    def y_view():
        y_log.append(1)
        return str(y())

    create_effect(x, lambda _v: set_x_runs(len(x_log)))
    create_effect(y, lambda _v: set_y_runs(len(y_log)))

    # `{f"Hello, {first()} {last()}!"}` is one derived expression and one
    # hole; `{node_hole()}` re-renders a node; `{x_view()}` is a call the
    # compiler turns into its own hole.
    return html(t"""
      <div data-testid="page-holes">
        <h2>Holes</h2>
        <div>
          <p>text: <span data-testid="hole-text">{count()}</span></p>
          <p>times ten: <span data-testid="hole-times-ten">{count() * 10}</span></p>
          <button data-testid="hole-text-inc" onclick={(lambda e: set_count(lambda n: n + 1))}>+1</button>
        </div>
        <div>
          <input data-testid="hole-first" value={first()} oninput={(lambda e: set_first(e.target.value))}>
          <input data-testid="hole-last" value={last()} oninput={(lambda e: set_last(e.target.value))}>
          <span data-testid="hole-greeting">{f"Hello, {first()} {last()}!"}</span>
        </div>
        <div>
          <p>node: <span data-testid="hole-node">{node_hole()}</span></p>
          <button data-testid="hole-node-cycle" onclick={next_mode}>cycle</button>
        </div>
        <div>
          <p>
            x: <span data-testid="hole-x">{x_view()}</span>{" "}
            runs: <span data-testid="hole-x-runs">{x_runs()}</span>
          </p>
          <p>
            y: <span data-testid="hole-y">{y_view()}</span>{" "}
            runs: <span data-testid="hole-y-runs">{y_runs()}</span>
          </p>
          <button data-testid="hole-x-inc" onclick={(lambda e: set_x(lambda n: n + 1))}>inc x</button>
          <button data-testid="hole-y-inc" onclick={(lambda e: set_y(lambda n: n + 1))}>inc y</button>
        </div>
      </div>
    """)
