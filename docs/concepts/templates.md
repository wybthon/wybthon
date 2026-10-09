# Templates

[`html`][wybthon.html] is how you write markup in Wybthon. It takes a [PEP 750](https://peps.python.org/pep-0750/) template string, the `t"..."` literal Python 3.14 added, and returns a node you can return from a component, pass as a child, or render.

```python
from wybthon import component, create_signal, html


@component
def Counter():
    count, set_count = create_signal(0)

    def increment():
        set_count(lambda n: n + 1)

    return html(t"""
      <div class="counter">
        <p>Count: {count}</p>
        <button onclick={increment}>+</button>
      </div>
    """)
```

The template is ordinary HTML. Each `{...}` is a Python expression, checked by your type checker like any other code, and placed where it appears in the markup.

## Why templates

Templates are Wybthon's counterpart of Solid's JSX, and they're also what makes Wybthon fast.

A t-string's static strings are a constant of the code that contains it, so every call of the same literal hands Wybthon the *same* strings object. Wybthon parses and compiles each literal once, keyed by that identity:

- The static markup becomes a native `<template>` that the JavaScript kernel clones with a single command per instance.
- Each interpolation becomes a slot at a known node offset.
- Mounting an instance builds no VNode tree for its static parts and checks nothing node by node: the literal guarantees its own structure.

That's the job Solid's compiler does for JSX, done by the language with no build step. It's also why Solid's buildless `html` tagged template looks the way it does.

## Interpolations

| Position | Example | What happens |
| --- | --- | --- |
| Child | `<p>{value}</p>` | Text, a node, a list, or `None`. A reactive expression becomes a hole. |
| Attribute | `<a href={url}>` | Applied once, or bound when reactive. |
| Part of an attribute | `<div class="card card-{kind}">` | The parts form one string; reactive parts make it one binding. |
| Event | `<button onclick={save}>` | A delegated handler. `onClick` and `on:click` work too. |
| Ref | `<input ref={field}>` | A [`Ref`][wybthon.Ref] or a callback that receives the element. |
| Spread | `<input {attrs}>` | A mapping of props applied to the element. |
| Component tag | `<{Card} title="Hi">...</{Card}>` | Calls the component; see [Components in templates](#components-in-templates). |

A **reactive expression** is an [`Accessor`][wybthon.Accessor] or a zero-argument function, exactly as with the [element helpers](../api/elements.md): put a signal in the template and only that text node or attribute updates when it changes. Anything else is applied once.

```python
count, set_count = create_signal(0)
kind, set_kind = create_signal("primary")
is_saving, set_saving = create_signal(False)

html(t'<button class="btn btn-{kind}" disabled={is_saving}>Saved {count} times</button>')
```

### Lambdas need parentheses

Python's grammar doesn't allow a bare `lambda` inside `{...}`, because the `:` would start a format spec. Wrap it in parentheses, or, usually more readable, give it a name:

```python
html(t"<p>{(lambda: count() * 2)}</p>")

doubled = create_memo(lambda: count() * 2)
html(t"<p>{doubled}</p>")
```

Named handlers and memos read better than inline lambdas anyway, and they're the idiomatic form in these docs.

### Conversions and format specs

They work as in any t-string, and they're re-applied when a reactive value changes:

```python
html(t"<td>{price:.2f}</td><td>{name!r}</td>")
```

## Markup rules

Templates are HTML, with a few conveniences borrowed from JSX:

- Attribute names are HTML names: `class`, `for`, `aria-label`, `data-id`, `tabindex`. Static values are written into the compiled markup.
- Any element may self-close (`<div />`). Void elements (`<br>`, `<input>`, `<img>`) may be written either way.
- Text follows JSX's whitespace rules. Text that spans lines is trimmed line by line and joined with single spaces, and whitespace-only text containing a newline is dropped, so you can indent markup freely. `<pre>` keeps its text verbatim.
- Character references such as `&amp;` and `&nbsp;` are decoded.
- `<!-- comments -->` are dropped.
- `<script>`, `<style>`, and `<textarea>` take static content only. Give a `<textarea>` its value with `value={...}`.

A template with several top-level nodes returns a fragment, and a template with no elements is text:

```python
html(t"<dt>{term}</dt><dd>{definition}</dd>")
html(t"Hello, {name}!")
```

### Markup the parser would rewrite is an error

Wybthon hands each template's markup to the browser's HTML parser and relies on getting back exactly the nodes it wrote. Markup the parser would silently rearrange raises [`TemplateError`][wybthon.TemplateError] the first time the template is used, with the template's source and the fix:

| Markup | Why it's rejected |
| --- | --- |
| `<table><tr>...</tr></table>` | The parser inserts a `<tbody>`; write it yourself. |
| `<p><div>...</div></p>` | A `<div>` closes the open `<p>`. |
| `<a><span><a>...</a></span></a>` | Links, buttons, and forms can't nest. |
| `<ul><li><li>...</li></li></ul>` | A `<li>` closes the previous one. |
| `<tbody>text</tbody>` | Table sections can't hold text. |
| `<div><span></div>` | Mismatched or unclosed tags. |

## Components in templates

There are two ways to use a component in a template. Calling it inside an interpolation keeps full type checking of its props:

```python
html(t"""
  <main>
    {Header(title="Dashboard", user=user)}
    {For(panels, Panel)}
  </main>
""")
```

The tag form reads like the rest of the markup and passes nested markup as `children`:

```python
html(t"""
  <{Card} title="Settings">
    <p>Changes apply immediately.</p>
    <button onclick={reset}>Reset</button>
  </{Card}>
""")
```

Attributes become keyword props (a hyphen becomes an underscore, and `class` and `for` become `class_` and `html_for`), and the content becomes the `children` prop, one child per top-level node. The built-ins work the same way, called the way their signatures take children:

```python
html(t"""
  <{Show} when={user} fallback={sign_in}>
    <p>Welcome back.</p>
  </{Show}>
  <{Theme} value="dark"><{Toolbar} /></{Theme}>
  <{Link} href="/settings" class="nav">Settings</{Link}>
""")
``` Close the tag with `</{Card}>`, or self-close it with `<{Card} />`. Type checkers can't see inside the template string, so the tag form's props are checked at run time in dev mode, like any component call. Use the call form when you want the checker's help.

## Templates and reactivity

A component runs once, so the template it returns is mounted once; only its reactive slots ever change. When a reactive *hole* returns a template, the hole re-runs when its inputs change. If it returns an instance of the same literal, Wybthon patches the mounted instance slot by slot, comparing each value with the previous one, the way lit-html does:

```python
html(t"<div>{(lambda: html(t'<b title={user().role}>{user().name}</b>'))}</div>")
```

Here a change to `user` writes only the attribute and text that changed. A template from a different literal replaces the instance.

You rarely need this: placing the accessors themselves in the template (`<b title={role}>{name}</b>`) gives each its own binding and no re-run at all.

## Templates and the element helpers

The [element helpers](../api/elements.md) (`div(...)`, `p(...)`, and the rest) are the programmatic layer, the counterpart of Solid's `h`. Use them when markup is built by code: generated forms, recursive trees, or components that compute their tag. The two mix freely, and they share one set of prop appliers, so a prop means the same thing in both:

```python
html(t"<ul>{[li(item) for item in items]}</ul>")
div(html(t"<h1>Title</h1>"), class_="page")
```

Helpers keep Python names for attributes (`class_`, `html_for`, `aria_label`). Templates use the HTML names.

## Server rendering, hydration, and SVG

A server render, a hydrating client, and SVG or MathML content expand a template into the same VNodes the element helpers would build and mount those, so output and hydration keys are identical whichever style you use. Everything else, which is every browser update after hydration, uses the compiled path.

## Editor support

Python expressions inside `{...}` are highlighted and type-checked as code. The surrounding HTML is a string, so editors don't highlight or format it unless you add an extension for HTML in t-strings.

## See also

- [Components](components.md): props, children, and the run-once model.
- [Virtual DOM](vdom.md): how compiled templates mount and update.
- [`html` API reference](../api/templates.md).
