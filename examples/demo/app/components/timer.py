from wybthon import Component, h, signal


class Timer(Component):
    def __init__(self, props):
        super().__init__(props)
        self.seconds = signal(0)

        # Create a JS interval and clean it up on unmount
        try:
            from js import clearInterval, setInterval
            from pyodide.ffi import create_proxy

            def tick():
                self.seconds.set(self.seconds.get() + 1)

            tick_proxy = create_proxy(lambda: tick())
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

            self.on_cleanup(cleanup)
        except Exception:
            # Non-browser or setup failure: no interval, still renders static value
            pass

    def render(self):
        return h("div", {"class": "timer"}, f"Seconds: {self.seconds.get()}")
