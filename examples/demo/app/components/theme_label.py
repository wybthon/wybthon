from app.contexts.theme import Theme
from wybthon import component, dynamic, p, use_context


@component
def ThemeLabel():
    """Display the current theme.

    With the new reactive context model the Provider's value is signal-
    backed, so wrapping the read in :func:`dynamic` keeps the label in
    sync as the theme flips -- no parent re-mount required.
    """
    return p(dynamic(lambda: f"Theme: {use_context(Theme)}"))
