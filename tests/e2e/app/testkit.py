"""Small helpers shared across E2E fixture feature pages.

``tid`` builds a stable ``data-testid`` attribute as a props mapping, for
places that compute the id: spread it onto an element or a component tag
in a template (``<div {tid(f"row-{n}")}>``). A literal id is simpler as a
plain attribute (``<div data-testid="row">``).
"""


def tid(name: str) -> dict[str, str]:
    """Return a props fragment that renders ``data-testid="<name>"``."""
    return {"data-testid": name}
