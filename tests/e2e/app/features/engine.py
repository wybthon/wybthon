"""Engine v2 surface: zero-argument handlers, t-strings, and typed components.

- Handlers may take no arguments (sync or async); the event is optional.
- A t-string with reactive interpolations is one binding that updates the
  whole string; one with only plain values renders as static text.
- ``Badge`` declares its inputs on a ``Props`` class: reactive ``Prop``
  fields the parent feeds with a signal, a derived function, and a plain
  value, plus plain fields for a callback and its test id.
"""

import asyncio
from collections.abc import Callable

from app.testkit import tid

from wybthon import Prop, Props, button, component, create_memo, create_signal, div, h2, p, prop, span


class BadgeProps(Props):
    label: Prop[str]
    count: Prop[int] = prop(default=0)
    tone: Prop[str] = prop(default="plain")
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

    return div(
        span(props.label, **tid(f"{props.test_id}-label")),
        span(props.count, **tid(f"{props.test_id}-count")),
        span(t"{props.label}={props.count} ({props.tone})", class_=t"tone-{props.tone}", **tid(f"{props.test_id}-t")),
        button("ping", on_click=ping, **tid(f"{props.test_id}-ping")),
        **tid(props.test_id),
    )


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

    return div(
        h2("Engine"),
        div(
            button("tap", on_click=tap, **tid("eng-tap")),
            button("tap (lambda)", on_click=lambda: set_taps(lambda n: n + 10), **tid("eng-tap-lambda")),
            button("tap (async)", on_click=tap_later, **tid("eng-tap-async")),
            span(taps, **tid("eng-taps")),
            span(async_taps, **tid("eng-async-taps")),
        ),
        div(
            p(t"Count: {count} (doubled: {doubled})", **tid("eng-t-count")),
            p(t"Price: {price:.2f}", **tid("eng-t-price")),
            p(t"Hello, {static_name}!", **tid("eng-t-static")),
            span("attr", title=t"count is {count}", class_=t"item item-{count}", **tid("eng-t-attr")),
            button("+1", on_click=lambda: set_count(lambda n: n + 1), **tid("eng-inc")),
            button("price", on_click=lambda: set_price(lambda v: v + 1.25), **tid("eng-price")),
        ),
        div(
            Badge(
                label=label,
                count=count,
                tone=lambda: "hot" if count() > 2 else "cold",
                on_ping=lambda n: set_received(f"ping {n}"),
            ),
            Badge(label="fixed", test_id="eng-badge-static"),
            span(received, **tid("eng-received")),
            button("rename", on_click=lambda: set_label("taps"), **tid("eng-rename")),
        ),
        **tid("page-engine"),
    )
