from app.contexts.theme import Theme
from wybthon import component, p, use_context


@component
def ThemeLabel():
    return p(f"Theme: {use_context(Theme)}")
