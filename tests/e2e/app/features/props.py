"""Reactive props: class, style, data attributes, and controlled inputs."""

from wybthon import component, create_signal, html

_COLORS = {"teal": "red", "red": "blue", "blue": "teal"}
_STATES = {"idle": "busy", "busy": "done", "done": "idle"}


@component
def Page():
    danger, set_danger = create_signal(False)
    color, set_color = create_signal("teal")
    state, set_state = create_signal("idle")
    text, set_text = create_signal("")
    checked, set_checked = create_signal(False)

    # Each dynamic attribute value is compiled into a binding: a
    # conditional string, a class mapping, a style mapping, a data
    # attribute, and controlled `value`/`checked` properties.
    return html(t"""
      <div data-testid="page-props">
        <h2>Props</h2>
        <div>
          <span class={ {"pill": True, "danger": danger()} } data-testid="props-class">status</span>
          <span class={"on" if danger() else ""} data-testid="props-class-on">flag</span>
          <button data-testid="props-class-btn" onclick={(lambda e: set_danger(lambda d: not d))}>toggle danger</button>
        </div>
        <div>
          <span style={ {"color": color()} } data-testid="props-style">colored</span>
          <button data-testid="props-style-btn" onclick={(lambda e: set_color(_COLORS[color()]))}>cycle color</button>
        </div>
        <div>
          <span data-state={state()} data-testid="props-attr">attr</span>
          <button data-testid="props-attr-btn" onclick={(lambda e: set_state(_STATES[state()]))}>cycle state</button>
        </div>
        <div>
          <input value={text()} oninput={(lambda e: set_text(e.target.value))} data-testid="props-input">
          <span data-testid="props-input-echo">{text()}</span>
          <button data-testid="props-input-set" onclick={(lambda e: set_text("hello"))}>set hello</button>
        </div>
        <div>
          <input
            type="checkbox"
            checked={checked()}
            onchange={(lambda e: set_checked(e.target.checked))}
            data-testid="props-check"
          >
          <span data-testid="props-check-echo">{"on" if checked() else "off"}</span>
        </div>
      </div>
    """)
