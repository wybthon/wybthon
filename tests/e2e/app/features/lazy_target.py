"""Lazy-loaded target component for the ``/lazy`` route.

Imported on demand by ``lazy(...)`` in :mod:`app.routes`; renders a marker
the harness can wait on once the component resolves.
"""

from app.testkit import tid

from wybthon import component, div, h2, span


@component
def LoadedPanel(query=None, params=None):
    return div(h2("Lazy"), span("lazy-loaded", **tid("lazy-loaded")), **tid("page-lazy"))
