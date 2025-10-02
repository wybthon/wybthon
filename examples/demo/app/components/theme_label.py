from app.contexts.theme import Theme
from wybthon import h, use_context


def ThemeLabel(_props):
    return h("p", {}, f"Theme: {use_context(Theme)}")
