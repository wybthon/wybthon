from wybthon import div, use_effect, use_state


def Timer(props):
    seconds, set_seconds = use_state(0)

    def setup_interval():
        try:
            from js import clearInterval, setInterval
            from pyodide.ffi import create_proxy

            tick_proxy = create_proxy(lambda: set_seconds(lambda s: s + 1))
            interval_id = setInterval(tick_proxy, 1000)

            def cleanup():
                try:
                    clearInterval(interval_id)
                except Exception:
                    pass
                try:
                    tick_proxy.destroy()
                except Exception:
                    pass

            return cleanup
        except Exception:
            return None

    use_effect(setup_interval, [])

    return div(f"Seconds: {seconds}", class_name="timer")
