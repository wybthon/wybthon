"""Derived state — temperature converter using memos.

Tweet caption:
    Two-way derived state, in Python. Type in Celsius, Fahrenheit updates.
    Type in Fahrenheit, Celsius updates. One source of truth either way.

Why it's interesting:
    Each input is bound to a separate signal, and `create_memo` computes
    the other unit. Edit either input and the other updates — without
    any manual sync, useEffect, or state machine.
"""

from wybthon import component, create_memo, create_signal, div, dynamic, input_, label, p


def _parse(text):
    try:
        return float(text)
    except ValueError:
        return None


@component
def TempConverter():
    celsius, set_celsius = create_signal("0")
    fahrenheit, set_fahrenheit = create_signal("32")

    def on_c(e):
        set_celsius(e.target.value)
        c = _parse(e.target.value)
        if c is not None:
            set_fahrenheit(f"{c * 9 / 5 + 32:g}")

    def on_f(e):
        set_fahrenheit(e.target.value)
        f = _parse(e.target.value)
        if f is not None:
            set_celsius(f"{(f - 32) * 5 / 9:g}")

    summary = create_memo(lambda: f"{celsius()} °C  =  {fahrenheit()} °F")

    return div(
        div(label("°C "), input_(value=celsius, on_input=on_c)),
        div(label("°F "), input_(value=fahrenheit, on_input=on_f)),
        p(dynamic(summary)),
    )
