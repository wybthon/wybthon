"""Stopwatch — start, stop, reset. In pure Python, in the browser.

Tweet caption:
    A complete stopwatch in 30 lines of Python. Start, stop, reset —
    and it cleans up the interval automatically when unmounted.

Why it's interesting:
    `on_mount` wires the interval, `on_cleanup` tears it down — no
    `useEffect` return-function dance. The `dynamic` text node is the
    only thing that updates each tick.
"""

from wybthon import button, component, create_signal, div, dynamic, on_cleanup, on_mount, p


@component
def Stopwatch():
    seconds, set_seconds = create_signal(0)
    running, set_running = create_signal(False)

    def tick():
        if running():
            set_seconds(seconds() + 1)

    def start():
        from js import clearInterval, setInterval
        from pyodide.ffi import create_proxy

        proxy = create_proxy(tick)
        tid = setInterval(proxy, 1000)
        on_cleanup(lambda: (clearInterval(tid), proxy.destroy()))

    on_mount(start)

    return div(
        p(dynamic(lambda: f"{seconds()}s")),
        button("Start", on_click=lambda e: set_running(True)),
        button("Stop", on_click=lambda e: set_running(False)),
        button("Reset", on_click=lambda e: set_seconds(0)),
    )
