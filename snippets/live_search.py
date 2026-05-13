"""Live search — filter a list as you type, with a derived signal.

Tweet caption:
    Live search-as-you-type, in Python, in the browser.
    Type a letter, the memo recomputes, only matching rows render.

Why it's interesting:
    `matches` is a `create_memo` — it auto-recomputes whenever `query`
    or `items` changes, and only that. `For` then diffs the result with
    per-item reactive scopes, so unchanged rows stay mounted.
"""

from wybthon import For, component, create_memo, create_signal, div, dynamic, input_, li, p, ul

LANGUAGES = [
    "Python",
    "JavaScript",
    "TypeScript",
    "Rust",
    "Go",
    "Ruby",
    "Elixir",
    "Haskell",
    "Zig",
    "Kotlin",
]


@component
def LiveSearch():
    query, set_query = create_signal("")
    matches = create_memo(lambda: [x for x in LANGUAGES if query().lower() in x.lower()])

    return div(
        input_(
            type="search",
            placeholder="Filter languages...",
            value=query,
            on_input=lambda e: set_query(e.target.value),
        ),
        p(dynamic(lambda: f"{len(matches())} match(es)")),
        ul(For(each=matches, children=lambda name, _i: li(name))),
    )
