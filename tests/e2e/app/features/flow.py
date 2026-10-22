"""Flow control: Show, For (keyed and positional modes), Repeat, Switch/Match, and dynamic.

Every control is called in a template, so the compiler passes each
dynamic argument as a getter: ``Show(visible(), ...)``,
``For(items(), row)``, and ``Match(status() == "ready", ...)`` stay
reactive without lambdas.
"""

from wybthon import For, Match, Repeat, Show, Switch, component, create_signal, dynamic, html

_NEXT_STATUS = {"idle": "loading", "loading": "ready", "ready": "idle"}
_NEXT_TAG = {"h3": "h2", "h2": "p", "p": "h3"}


def keyed_row(item, index):
    # Keyed by identity (strings match by value): rows move on reorder,
    # and the index accessor follows them.
    return html(t"<li>{index()}:{item}</li>")


def positional_row(item, index):
    # Positional: slots are reused and their item accessor updates.
    return html(t"<li>[{index}]{item()}</li>")


def star(i):
    return html(t"<li>star-{i}</li>")


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
    Heading = dynamic(tag)

    return html(t"""
      <div data-testid="page-flow">
        <h2>Flow</h2>
        <div>
          <button data-testid="flow-show-toggle" onclick={(lambda e: set_visible(lambda v: not v))}>toggle</button>
          {
        Show(
            visible(),
            html(t'<span data-testid="flow-show-on">shown</span>'),
            fallback=html(t'<span data-testid="flow-show-off">hidden</span>'),
        )
    }
        </div>
        <div>
          <button data-testid="flow-for-add" onclick={add}>add</button>
          <button data-testid="flow-for-remove" onclick={remove_last}>remove</button>
          <button data-testid="flow-for-reverse" onclick={reverse}>reverse</button>
          <span data-testid="flow-for-count">{len(items())}</span>
          {Show(len(items()) > 3, html(t'<span data-testid="flow-for-many">many</span>'))}
          <ul data-testid="flow-for-list">{For(items(), keyed_row)}</ul>
          <ul data-testid="flow-index-list">{For(items(), positional_row, keyed=False)}</ul>
        </div>
        <div>
          <button data-testid="flow-repeat-inc" onclick={(lambda e: set_stars(lambda n: n + 1))}>star +</button>
          <button data-testid="flow-repeat-dec" onclick={(lambda e: set_stars(lambda n: max(0, n - 1)))}>star -</button>
          <ul data-testid="flow-repeat-list">{Repeat(stars(), star, fallback=html(t"<li>no stars</li>"))}</ul>
        </div>
        <div>
          <button data-testid="flow-switch-cycle" onclick={(lambda e: set_status(_NEXT_STATUS[status()]))}>
            cycle status
          </button>
          {
        Switch(
            Match(status() == "loading", html(t'<span data-testid="flow-switch-out">loading</span>')),
            Match(status() == "ready", html(t'<span data-testid="flow-switch-out">ready</span>')),
            fallback=html(t'<span data-testid="flow-switch-out">idle</span>'),
        )
    }
        </div>
        <div>
          <button data-testid="flow-dyn-cycle" onclick={(lambda e: set_tag(_NEXT_TAG[tag()]))}>cycle tag</button>
          <{Heading} data-testid="flow-dyn-out">dyn</{Heading}>
        </div>
      </div>
    """)
