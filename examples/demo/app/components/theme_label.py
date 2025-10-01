from wybthon import h, use_context
from app.contexts.theme import Theme


def ThemeLabel(_props):
    return h("p", {}, f"Theme: {use_context(Theme)}")
