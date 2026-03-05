from app.contexts.theme import Theme
from wybthon import p, use_context


def ThemeLabel(_props):
    return p(f"Theme: {use_context(Theme)}")
