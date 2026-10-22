"""Portal: render children into a different DOM container while staying reactive."""

from wybthon import Portal, Show, component, create_signal, html


@component
def Page():
    show, set_show = create_signal(False)
    count, set_count = create_signal(0)

    def content():
        return html(t'<div data-testid="portal-content"><span data-testid="portal-count">{count()}</span></div>')

    return html(t"""
      <div data-testid="page-portal">
        <h2>Portal</h2>
        <button data-testid="portal-toggle" onclick={(lambda e: set_show(lambda v: not v))}>toggle</button>
        <button data-testid="portal-inc" onclick={(lambda e: set_count(lambda n: n + 1))}>inc</button>
        <div data-testid="portal-source">{Show(show(), Portal(content(), mount="#portal-target-inner"))}</div>
        <div data-testid="portal-target"><div id="portal-target-inner" data-testid="portal-target-inner"></div></div>
      </div>
    """)
