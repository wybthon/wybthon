"""Single source of truth for the fixture's feature routes.

Both the navigation shell and the route table consume ``FEATURES`` so the
two never drift. Each entry is ``(slug, label)``; the slug doubles as the
route path (``/<slug>``), the nav test id (``nav-<slug>``), and the page
marker test id (``page-<slug>``) that the Playwright harness waits on.
"""

FEATURES = [
    ("contracts", "Contracts"),
    ("reactivity", "Reactivity"),
    ("holes", "Holes"),
    ("props", "Props"),
    ("events", "Events"),
    ("context", "Context"),
    ("flow", "Flow"),
    ("forms", "Forms"),
    ("stores", "Stores"),
    ("loading", "Loading"),
    ("transitions", "Transitions"),
    ("errors", "Errors"),
    ("components", "Components"),
    ("lazy", "Lazy"),
    ("portal", "Portal"),
    ("router", "Router"),
]
