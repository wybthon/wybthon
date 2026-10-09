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

- **No em dashes** (U+2014). Use commas, parentheses, semicolons, colons,
  or full sentences instead. The exact replacement depends on context: use
  a pair of commas for a brief aside, parentheses for a longer one, a colon
  before a list or amplification, and a semicolon between two related
  independent clauses.
- **Use straight ASCII quotes and apostrophes** (`"` and `'`), not the
  typographic curly forms (U+2018, U+2019, U+201C, U+201D). This keeps
  prose copy-pasteable into source code, terminals, and search.
- **Use contractions** where they read naturally (`it's`, `don't`,
  `you'll`); the docs are conversational, not legal text.
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
def repeat(count, fn, *, start=0, fallback=None):
    """Map an integer range to rows, each with its own owner scope.

    The counterpart of Solid 2.0's `repeat`: `fn(i)` runs once per slot
    for `i` in `range(start, start + count)`. Growing the count maps only
    the new slots; shrinking it disposes the removed ones.

    Args:
        count: The number of slots, or an accessor for it.
        fn: Maps one slot number to a row.
        start: The first slot number, or an accessor for it.
        fallback: Optional zero-arg callable whose result is the single
            row when the count is zero.

    Returns:
        A memo yielding the list of mapped rows.

    Example:
        ```python
        count, set_count = create_signal(3)
        rows = repeat(count, lambda i: html(t"<li>Row {i}</li>"))
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
class Field[T]:
    """Reactive state for one form field: value, error, and touched.

    Attributes:
        value: Accessor for the current input value.
        set_value: Setter for the value.
        error: Accessor for the latest validation error, or `None`.
        set_error: Setter for the error.
        touched: Accessor that's `True` once the user has interacted
            with the field, so error display can wait until they have.
        set_touched: Setter for the touched flag.

    Example:
        ```python
        fields = form_state({"name": ""})
        name = fields["name"]
        html(t"<input {bind_text(name)}><span>{name.error}</span>")
        ```
    """
```

The class summary describes the type's purpose. Document construction in
`__init__` only when there's more to say than the signature already conveys
(set `merge_init_into_class: true` in mkdocstrings; already configured).

### Module

Every module should open with a one-line summary, an extended description,
and (when illustrative) a small example:

```python
"""Reactive list mapping helpers.

[`map_array`][wybthon.map_array] is the engine behind
[`For`][wybthon.For] and [`Repeat`][wybthon.Repeat]: it turns a
reactive list into a memoized list of mapped rows, reusing each row's
owner scope across updates so per-row state survives reorders.

Example:
    ```python
    items, set_items = create_signal(["A", "B"])
    labels = map_array(items, lambda item, idx: f"{idx()}: {item}")
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
``(getter, setter)`` tuple. See [`create_memo`][wybthon.create_memo]
for async data.
```

Inside a docstring, plain backticks plus the qualified name are
typically enough; autorefs picks them up via signature annotations
(`signature_crossrefs: true`).

## Code samples

- Always tag the language: ` ```python `, ` ```bash `, ` ```html `,
  ` ```yaml `.
- Prefer **runnable** snippets that include the imports needed to
  copy-paste them.
- Write markup as [`html`][wybthon.html] templates. Use the element
  helpers (`div(...)`, `h(...)`) only where the page is about them or
  the markup is built by code.
- Never put a bare `lambda` inside a t-string interpolation; it's a
  `SyntaxError`. Prefer a named function or memo, and wrap an inline
  lambda in parentheses when one is clearer: `{(lambda: count() * 2)}`.
- Check that every template parses: `<tr>` needs a `<tbody>`, and a
  `<p>` can't hold block elements. Malformed markup raises
  [`TemplateError`][wybthon.TemplateError].
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
- Manage async data: [`create_memo`][wybthon.create_memo]
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
