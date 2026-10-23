"""Errored: catch a child render error, show fallback, and reset to recover."""

from wybthon import Errored, component, create_signal, html


@component
def Page():
    should_throw, set_should_throw = create_signal(True)
    reset_key, set_reset_key = create_signal(0)

    @component
    def Bug():
        # A one-time read: the boundary remounts this component on reset.
        if should_throw.peek():
            raise RuntimeError("boom")
        return html(t'<span data-testid="err-ok">recovered</span>')

    def fallback(err, reset):
        return html(t"""
          <div>
            <span data-testid="err-fallback">caught: {err()}</span>
            <button data-testid="err-retry" onclick={reset}>retry</button>
          </div>
        """)

    def fix_and_reset():
        set_should_throw(False)
        set_reset_key(lambda n: n + 1)

    return html(t"""
      <div data-testid="page-errors">
        <h2>Errors</h2>
        {Errored(html(t"<div><{Bug} /></div>"), fallback=fallback, reset_on=reset_key())}
        <button data-testid="err-fix" onclick={fix_and_reset}>fix + reset</button>
      </div>
    """)
