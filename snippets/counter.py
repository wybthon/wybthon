"""Counter — the "hello world" of frontend frameworks, in pure Python.

Tweet caption:
    A reactive counter in 8 lines of Python — running in the browser.
    No JavaScript, no build step, no JSX. Just Python and Wybthon.

Why it's interesting:
    The component body runs ONCE. `count` is a zero-arg getter that
    becomes a reactive hole inside `span(...)` — only that text node
    updates when you click. No re-renders.
"""

from wybthon import button, component, create_signal, div, p, span


@component
def Counter():
    count, set_count = create_signal(0)

    return div(
        p("Count: ", span(count)),
        button("+1", on_click=lambda e: set_count(count() + 1)),
    )
