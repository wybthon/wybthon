"""Dark mode toggle — reactive context, no prop drilling.

Tweet caption:
    A dark mode toggle in Python using reactive context. Change the
    provider value once; every consumer updates. No re-mounts.

Why it's interesting:
    `create_context` + `Provider` give you a signal-backed shared value.
    `use_context` returns the current value AND subscribes the caller,
    so only the consumers that read it re-run when it changes.
"""

from wybthon import (
    button,
    component,
    create_context,
    create_signal,
    div,
    dynamic,
    h,
    p,
    use_context,
)
from wybthon.context import Provider

Theme = create_context("light")


@component
def ThemedCard():
    theme = use_context(Theme)
    return div(
        p(dynamic(lambda: f"Current theme: {theme}")),
        style=lambda: {
            "padding": "16px",
            "background": "#111" if theme == "dark" else "#f7f7f7",
            "color": "#eee" if theme == "dark" else "#111",
        },
    )


@component
def App():
    theme, set_theme = create_signal("light")

    return div(
        button(
            dynamic(lambda: f"Switch to {'light' if theme() == 'dark' else 'dark'}"),
            on_click=lambda e: set_theme("dark" if theme() == "light" else "light"),
        ),
        h(Provider, {"context": Theme, "value": theme}, h(ThemedCard, {})),
    )
