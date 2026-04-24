# Documentation style guide

This page describes how Wybthon's documentation and source-level docstrings
are written. Follow it when authoring new code or revising existing pages
so the site renders consistently and `help()` reads cleanly inside a
Pyodide REPL.

## TL;DR

- Use **Google-style** docstrings everywhere (modules, classes, functions).
- Let type hints carry the types. Don't repeat them inside docstrings.
- Use Material **admonitions** (`!!! tip "Title"`) for callouts in
  Markdown, not plain `>` blockquotes.
- Cross-link API symbols using mkdocstrings autorefs:
  `` [`create_signal`][wybthon.create_signal] ``.
- Comments explain **why**, not **what** (the code already says what).

## Grammar and punctuation

We follow the *Chicago Manual of Style* (17th edition) for prose. Highlights:

- **No em dashes (`—`).** Use commas, parentheses, semicolons, colons, or
  full sentences instead. The exact replacement depends on context: use a
  pair of commas for a brief aside, parentheses for a longer one, a colon
  before a list or amplification, and a semicolon between two related
  independent clauses.
- **Use straight ASCII quotes and apostrophes** (`"` and `'`), not curly
  quotes (`"`, `"`, `'`, or `'`). This keeps prose copy-pasteable into
  source code, terminals, and search.
- Use the **serial (Oxford) comma** in lists of three or more.
- Spell out **e.g.** and **i.e.** with periods and follow them with a
  comma: `e.g., a counter component`.
- Hyphenate compound modifiers before a noun (`fine-grained reactivity`,
  `single-page application`) but not after (`reactivity is fine grained`).
- Use **sentence case** for headings and titles: only the first word and
  proper nouns are capitalized.

## Docstrings: Google style

Wybthon follows the
[Google Python Style Guide](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings).
The `mkdocstrings` plugin is configured for Google style and renders
the standard sections as tables.

### Function or method

```python
def map_array(source, map_fn):
    """Map a reactive list with stable per-item scopes.

    Items are matched by **reference identity**. The mapping callback
    runs **once** per unique item; when an item leaves the source list,
    its reactive scope is disposed automatically.

    Args:
        source: A zero-arg getter that returns the current list. Tracking
            is established when the returned getter is read inside a
            reactive computation.
        map_fn: Called as ``map_fn(item_getter, index_getter)`` for each
            unique item. ``item_getter()`` returns the item; ``index_getter()``
            returns its current position.

    Returns:
        A zero-arg getter that, when read, returns the mapped list.

    Raises:
        TypeError: If ``source`` is not callable.

    Example:
        ```python
        items, set_items = create_signal(["A", "B", "C"])
        labels = map_array(items, lambda item, idx: f"{idx()}: {item()}")
        # labels() == ["0: A", "1: B", "2: C"]
        ```
    """
```

Notes:

- The first line is an **imperative summary** ending in a period.
- Leave one blank line between the summary and the extended description.
- Use these sections in order: `Args:`, `Returns:`, `Yields:`, `Raises:`,
  `Note:`, `Warning:`, `Example:`. Skip any that don't apply.
- **Don't repeat type annotations** inside `Args:`; the rendered API
  table pulls them from the function signature automatically.
- Inside `Example:`, use a fenced code block (` ```python `) with the
  imports needed to run the snippet so users can copy it directly.

### Class

```python
class Resource(Generic[R]):
    """Async resource with reactive ``data``, ``error``, and ``loading``.

    Wraps an awaitable fetcher and exposes signal-backed state so
    consumers can render loading and error UIs declaratively (see
    ``Suspense``).

    Attributes:
        data: Reactive accessor for the most recent successful payload.
        error: Reactive accessor for the most recent error, or ``None``.
        loading: Reactive accessor; ``True`` while a fetch is in flight.

    Example:
        ```python
        async def load_user(signal=None):
            resp = await fetch("/api/users/1")
            return await resp.json()

        user = create_resource(load_user)
        h("p", {}, dynamic(lambda: "Loading..." if user.loading() else user.data().get("name")))
        ```
    """
```

The class summary describes the type's purpose. Document construction in
`__init__` only when there is more to say than the signature already conveys
(set `merge_init_into_class: true` in mkdocstrings; already configured).

### Module

Every module should open with a one-line summary, an extended description,
and (when illustrative) a small example:

```python
"""Reactive list helpers built on top of signals.

This module provides keyed (``map_array``) and indexed (``index_array``)
list mappings, plus an ``O(1)`` selection signal (``create_selector``).
Each helper integrates with the reactive ownership tree so per-item
scopes are disposed automatically when items leave the source list.

Example:
    ```python
    items, set_items = create_signal(["A", "B"])
    labels = map_array(items, lambda item, idx: f"{idx()}: {item()}")
    ```
"""
```

### Private helpers

Underscore-prefixed members (`_helper`) are filtered out of the public
API site (mkdocstrings `filters: ["!^_"]`). Keep their docstrings
short (one line is usually enough), but do write them: contributors
inspect them in editors and during code review.

## Comments: explain *why*

!!! quote "Rule of thumb"
    Comments are most useful when they explain things the reader cannot
    learn from the code itself.

Good comments:

- Document a non-obvious invariant or constraint.
- Explain a trade-off between two reasonable approaches.
- Cite an external spec, RFC, or upstream bug report.
- Warn about a subtle ordering requirement.

Bad comments (don't add them):

- Narrating what the next line does (`# increment counter`).
- Restating the function name (`# create the signal`).
- TODOs without an owner or issue link; open a tracking issue and link it.

When you find a redundant comment during a refactor, delete it. The
diff will be smaller and the code will be easier to read.

## Markdown: admonitions over blockquotes

Use Material admonitions for callouts. They render with an icon, a
colored block, and a collapsible variant:

```markdown
!!! note
    Plain note.

!!! tip "Pro tip"
    Custom-titled tip.

!!! warning
    Heads-up about a footgun.

??? info "Click to expand"
    Collapsed by default.
```

Reserve plain Markdown blockquotes (`>`) for *quoted text* (a quote
from the docs, a user, or an upstream project). Don't use them for
tips or warnings.

## Cross-linking

Mkdocstrings plus autorefs lets you link to any documented symbol from
plain Markdown. Prefer these short forms:

```markdown
The [`create_signal`][wybthon.create_signal] primitive returns a
``(getter, setter)`` tuple. See [`Resource`][wybthon.Resource] for
async data.
```

Inside a docstring, plain backticks plus the qualified name are
typically enough; autorefs picks them up via signature annotations
(`signature_crossrefs: true`).

## Code samples

- Always tag the language: ` ```python `, ` ```bash `, ` ```html `,
  ` ```yaml `.
- Prefer **runnable** snippets that include the imports needed to
  copy-paste them.
- For longer multi-step examples, lean on Material's `pymdownx.tabbed`
  to show the same example in different forms (e.g., "Component" vs.
  "Direct call").

## Page structure

A typical concept or guide page follows this skeleton:

1. `# Title`. H1 only on the page itself; the site nav supplies the
   parent heading.
2. **One-paragraph summary** of what this page covers and who it's for.
3. **Sections** (`##`, `###`) covering the topic in order of increasing
   depth. Lead with the simplest example.
4. **Next steps** at the bottom with cross-links to related pages,
   to keep the reader moving.

```markdown
## Next steps

- Build your first component: [Components](components.md)
- Manage async data: [`create_resource`][wybthon.create_resource]
- Performance tuning: [Performance guide](../guides/performance.md)
```

## Linting

Docstrings are checked by Ruff with the Google convention enabled:

```bash
ruff check src/wybthon
```

The relevant rule set lives in `pyproject.toml` under `[tool.ruff.lint]`.
The site build also runs in **strict mode** (`mkdocs build --strict`)
on every push to `main`, so missing cross-references and broken links
fail CI.
