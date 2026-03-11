from wybthon import component, create_signal, div, on_cleanup, on_mount


@component
def Timer():
    seconds, set_seconds = create_signal(0)

    tick_proxy = [None]
    interval_id = [None]

    def start():
        try:
            from js import setInterval
            from pyodide.ffi import create_proxy

            tick_proxy[0] = create_proxy(lambda: set_seconds(seconds() + 1))
            interval_id[0] = setInterval(tick_proxy[0], 1000)
        except Exception:
            pass

    def stop():
        try:
            from js import clearInterval

            if interval_id[0] is not None:
                clearInterval(interval_id[0])
        except Exception:
            pass
        try:
            if tick_proxy[0] is not None:
                tick_proxy[0].destroy()
        except Exception:
            pass

    on_mount(start)
    on_cleanup(stop)

    def render():
        return div(f"Elapsed: {seconds()}s", class_name="timer")

    return render
