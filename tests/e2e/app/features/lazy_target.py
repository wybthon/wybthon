"""Lazy-loaded target component for the ``/lazy`` route.

Imported on demand by ``lazy(...)`` in :mod:`app.routes`; renders a marker
the harness can wait on once the component resolves.
"""

from wybthon import component, html


@component
def LoadedPanel():
    return html(t'<div data-testid="page-lazy"><h2>Lazy</h2><span data-testid="lazy-loaded">lazy-loaded</span></div>')
