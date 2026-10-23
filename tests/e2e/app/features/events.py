"""Event delegation: bubbling, stopPropagation, and target value/checked reads."""

from wybthon import component, create_signal, html


@component
def Page():
    outer, set_outer = create_signal(0)
    inner, set_inner = create_signal(0)
    text, set_text = create_signal("")
    checked, set_checked = create_signal(False)

    def on_outer(_e):
        set_outer(lambda n: n + 1)

    def on_inner_stop(e):
        e.stop_propagation()
        set_inner(lambda n: n + 1)

    def on_inner_bubble(_e):
        set_inner(lambda n: n + 1)

    return html(t"""
      <div data-testid="page-events">
        <h2>Events</h2>
        <div data-testid="ev-outer" onclick={on_outer}>
          <p>outer clicks: <span data-testid="ev-outer-count">{outer()}</span></p>
          <p>inner clicks: <span data-testid="ev-inner-count">{inner()}</span></p>
          <button data-testid="ev-inner-stop" onclick={on_inner_stop}>inner (stop)</button>
          <button data-testid="ev-inner-bubble" onclick={on_inner_bubble}>inner (bubble)</button>
        </div>
        <div>
          <input data-testid="ev-input" oninput={(lambda e: set_text(e.target.value))}>
          <span data-testid="ev-input-echo">{text()}</span>
          <input type="checkbox" data-testid="ev-check" onchange={(lambda e: set_checked(e.target.checked))}>
          <span data-testid="ev-check-echo">{"on" if checked() else "off"}</span>
        </div>
      </div>
    """)
