"""Small helpers shared across E2E fixture feature pages.

``tid`` emits a stable ``data-testid`` attribute. Wybthon's HTML element
helpers pass arbitrary keyword props straight through, and CPython permits
spreading a dict with non-identifier keys into ``**kwargs``. That lets every
fixture use ``span("x", **tid("rx-value"))`` to attach a hyphenated test id
without reaching for the low-level ``h`` constructor.

Spread it onto elements only: components declare their props on a
``Props`` class and reject unknown names, so a component that needs a test
id declares an explicit field for it.
"""


def tid(name: str) -> dict[str, str]:
    """Return a props fragment that renders ``data-testid="<name>"``."""
    return {"data-testid": name}
