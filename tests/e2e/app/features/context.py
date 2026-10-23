"""Context API: provider value propagation, nested override, and default fallback."""

from wybthon import Props, component, create_context, create_signal, html, use_context

Theme = create_context("default-theme")


class ThemeLabelProps(Props):
    test_id: str


@component
def ThemeLabel(props: ThemeLabelProps):
    # The provided value is handed back as is: an accessor stays live, a
    # plain string renders once.
    theme = use_context(Theme)
    return html(t"<span data-testid={props.test_id}>{theme}</span>")


@component
def Page():
    theme, set_theme = create_signal("light")

    def toggle():
        set_theme(lambda t: "dark" if t == "light" else "light")

    # A context called in a template builds its provider; the signal is
    # passed through as is (a name isn't compiled into a getter).
    return html(t"""
      <div data-testid="page-context">
        <h2>Context</h2>
        {
        Theme(
            theme,
            html(t'''
          <div>
            <p>outer: <{ThemeLabel} test-id="ctx-outer" /></p>
            {Theme("override", html(t'<p>inner: <{ThemeLabel} test-id="ctx-inner" /></p>'))}
          </div>
        '''),
        )
    }
        <p>no provider: <{ThemeLabel} test-id="ctx-default" /></p>
        <button data-testid="ctx-toggle" onclick={toggle}>toggle</button>
      </div>
    """)
