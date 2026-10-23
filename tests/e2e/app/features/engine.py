"""Engine surface: zero-argument handlers, compiled expressions, and typed components.

- Handlers may take no arguments (sync or async); the event is optional.
- Dynamic expressions in a template (``{count() * 2}``, ``{price():.2f}``,
  ``title="count is {count()}"``) are compiled into getters, so each one
  updates its own text node or attribute; names and constants render
  as they are.
- ``Badge`` declares its inputs on a ``Props`` class with plain
  annotations. The parent feeds them with a compiled expression, a
  signal, a derived expression, and plain values, plus a callback field
  that's handed through untouched.
"""

import asyncio
from collections.abc import Callable

from wybthon import Props, component, create_memo, create_signal, html


class BadgeProps(Props):
    label: str
    count: int = 0
    tone: str = "plain"
    on_ping: Callable[[int], None] | None = None
    test_id: str = "eng-badge"


mounts = 0


@component
def Badge(props: BadgeProps):
    global mounts
    mounts += 1
    pings, set_pings = create_signal(0)

    def ping():
        set_pings(lambda n: n + 1)
        if props.on_ping is not None:
            props.on_ping(pings.peek() + 1)

    return html(t"""
      <div data-testid={props.test_id}>
        <span data-testid="{props.test_id}-label">{props.label}</span>
        <span data-testid="{props.test_id}-count">{props.count}</span>
        <span data-testid="{props.test_id}-t" class="tone-{props.tone}">
          {props.label}={props.count} ({props.tone})
        </span>
        <button data-testid="{props.test_id}-ping" onclick={ping}>ping</button>
      </div>
    """)


@component
def Page():
    taps, set_taps = create_signal(0)
    async_taps, set_async_taps = create_signal(0)
    count, set_count = create_signal(1)
    doubled = create_memo(lambda: count() * 2)
    price, set_price = create_signal(3.5)
    label, set_label = create_signal("clicks")
    received, set_received = create_signal("none")
    static_name = "Ada"

    def tap():
        set_taps(lambda n: n + 1)

    async def tap_later():
        await asyncio.sleep(0)
        set_async_taps(lambda n: n + 1)

    return html(t"""
      <div data-testid="page-engine">
        <h2>Engine</h2>
        <div>
          <button data-testid="eng-tap" onclick={tap}>tap</button>
          <button data-testid="eng-tap-lambda" onclick={(lambda: set_taps(lambda n: n + 10))}>tap (lambda)</button>
          <button data-testid="eng-tap-async" onclick={tap_later}>tap (async)</button>
          <span data-testid="eng-taps">{taps()}</span>
          <span data-testid="eng-async-taps">{async_taps()}</span>
        </div>
        <div>
          <p data-testid="eng-t-count">Count: {count()} (doubled: {count() * 2})</p>
          <p data-testid="eng-t-memo">Memo: {doubled}</p>
          <p data-testid="eng-t-price">Price: {price():.2f}</p>
          <p data-testid="eng-t-static">Hello, {static_name}!</p>
          <span data-testid="eng-t-attr" title="count is {count()}" class="item item-{count()}">attr</span>
          <button data-testid="eng-inc" onclick={(lambda: set_count(lambda n: n + 1))}>+1</button>
          <button data-testid="eng-price" onclick={(lambda: set_price(lambda v: v + 1.25))}>price</button>
        </div>
        <div>
          {
        Badge(
            label=label(),
            count=count,
            tone="hot" if count() > 2 else "cold",
            on_ping=lambda n: set_received(f"ping {n}"),
        )
    }
          <{Badge} label="fixed" test-id="eng-badge-static" />
          <span data-testid="eng-received">{received()}</span>
          <button data-testid="eng-rename" onclick={(lambda: set_label("taps"))}>rename</button>
        </div>
      </div>
    """)
