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
        <p>Count: {count()} (doubled: {count() * 2})</p>
        <button onclick={increment}>+</button>
      </div>
    """)
```

The template is ordinary HTML. Each `{...}` is a Python expression, checked by your type checker like any other code, and placed where it appears in the markup. Wybthon's [compiler](compiler.md) makes each dynamic expression, such as `{count() * 2}`, a getter, so that text node updates whenever `count` changes, and nothing else does.

## Why templates

Templates are Wybthon's counterpart of Solid's JSX, and they're also what makes Wybthon fast.

A t-string's static strings are a constant of the code that contains it, so Wybthon can treat each literal as a fixed piece of markup. The compiler parses and validates each literal when its module is compiled and writes the result into the module:

- The static markup becomes a native `<template>` that the JavaScript kernel clones with a single command per instance.
- Each interpolation becomes a slot at a known node offset, and each dynamic expression becomes a getter for that slot.
- Each element gets a mount function, written as ordinary Python, so mounting an instance builds no VNode tree for its static parts and checks nothing node by node: the literal guarantees its own structure.

That's the job Solid's compiler does for JSX. A production build never parses a template or generates code at run time. A template that reaches `html()` uncompiled, in a REPL for example, is compiled on its first call and cached; see [Templates that weren't compiled](compiler.md#templates-that-werent-compiled).

## Interpolations

| Position | Example | What happens |
| --- | --- | --- |
| Child | `<p>{value}</p>` | Text, a node, a list, or `None`. A dynamic expression or an accessor becomes a hole. |
| Attribute | `<a href={url()}>` | Applied once, or bound when dynamic or an accessor. |
| Part of an attribute | `<div class="card card-{kind()}">` | The parts form one string; dynamic parts make it one binding. |
| Event | `<button onclick={save}>` | A delegated handler. `onClick` and `on:click` work too. |
| Ref | `<input ref={field}>` | A [`Ref`][wybthon.Ref] or a callback that receives the element. |
| Spread | `<input {attrs}>` | A mapping of props applied to the element. |
| Component tag | `<{Card} title="Hi">...</{Card}>` | Calls the component; see [Components in templates](#components-in-templates). |

An expression is **dynamic** when it contains a call, an attribute access, or a subscript: `{count()}`, `{count() * 2}`, `{props.title}`, `{row["label"]}`, `class={"on" if active() else ""}`. The compiler turns it into a getter, so only that text node or attribute updates when what it reads changes. A name or a constant is a value, and an [`Accessor`][wybthon.Accessor] or a lambda is still a reactive expression, so `{count}` and `{count()}` both update. Event handlers, refs, and spreads are never wrapped. The [compiler page](compiler.md#the-rule-dynamic-or-static) has the full rule.

```python
count, set_count = create_signal(0)
kind, set_kind = create_signal("primary")
is_saving, set_saving = create_signal(False)

html(t'<button class="btn btn-{kind()}" disabled={is_saving()}>Saved {count()} times</button>')
```

### Lambdas need parentheses

With the compiler you rarely write a lambda in a template, but you still need one for an inline event handler. Python's grammar doesn't allow a bare `lambda` inside `{...}`, because the `:` would start a format spec. Wrap it in parentheses, or, usually more readable, give it a name:

```python
html(t"<button onclick={(lambda: set_open(False))}>Close</button>")


def close():
    set_open(False)


html(t"<button onclick={close}>Close</button>")
```

Named handlers read better than inline lambdas, and they're the idiomatic form in these docs. A lambda in a child or attribute position (`{(lambda: count() * 2)}`) is a reactive expression, exactly like the plain `{count() * 2}`.

### Conversions and format specs

They work as in any t-string. The compiler folds them into the getter, so they're re-applied when the value changes:

```python
html(t"<td>{price():.2f}</td><td>{name()!r}</td>")
```

## Markup rules

Templates are HTML, with a few conveniences borrowed from JSX:

- Attribute names are HTML names: `class`, `for`, `aria-label`, `data-id`, `tabindex`. Static values are written into the compiled markup.
- Any element may self-close (`<div />`). Void elements (`<br>`, `<input>`, `<img>`) may be written either way.
- Text follows JSX's whitespace rules. Text that spans lines is trimmed line by line and joined with single spaces, and whitespace-only text containing a newline is dropped, so you can indent markup freely. `<pre>` keeps its text verbatim.
- Character references such as `&amp;` and `&nbsp;` are decoded.
- `<!-- comments -->` are dropped.
- `<script>`, `<style>`, and `<textarea>` take static content only. Give a `<textarea>` its value with `value={...}`.
- `<svg>` and `<math>` work like any other element, and their children get the right namespace.

A template with several top-level nodes returns a fragment, and a template with no elements is text:

```python
html(t"<dt>{term}</dt><dd>{definition}</dd>")
html(t"Hello, {name}!")
```

### Markup the parser would rewrite is an error

Wybthon hands each template's markup to the browser's HTML parser and relies on getting back exactly the nodes it wrote. Markup the parser would silently rearrange is rejected with the template's source and the fix. The compiler reports it as a `SyntaxError` with the file and line when the module is compiled; a template compiled at run time raises [`TemplateError`][wybthon.TemplateError] the first time it's used:

| Markup | Why it's rejected |
| --- | --- |
| `<table><tr>...</tr></table>` | The parser inserts a `<tbody>`; write it yourself. |
| `<p><span><div>...</div></span></p>` | A block element closes an open `<p>`, however deeply it's nested (a `<button>` or table cell in between stops this). |
| `<a><span><a>...</a></span></a>` | Links, buttons, and forms can't nest. |
| `<li><div><li>...</li></div></li>` | A `<li>` closes an open one unless a list wraps it; `<dd>` and `<dt>` work the same way inside a `<dl>`. |
| `<tbody>text</tbody>` | Table sections can't hold text. |
| `<div><span></div>` | Mismatched or unclosed tags. |

## Components in templates

There are two ways to use a component in a template. Calling it inside an interpolation keeps full type checking of its props:

```python
html(t"""
  <main>
    {Header(title="Dashboard", user=user())}
    {For(panels(), panel_row)}
  </main>
""")
```

A call in a child position is dispatched when the template is created: a component, or a built-in such as `Show` or `For`, is built with a getter for each dynamic argument, so `Header` reads `props.user` and sees each new value of `user()`. Any other call, such as `{format_date(created())}`, becomes one reactive hole. See [Calls in a child position](compiler.md#calls-in-a-child-position).

The tag form reads like the rest of the markup and passes nested markup as `children`:

```python
html(t"""
  <{Card} title={project().name}>
    <p>Changes apply immediately.</p>
    <button onclick={reset}>Reset</button>
  </{Card}>
""")
```

Attributes become keyword props (a hyphen becomes an underscore, and `class` and `for` become `class_` and `html_for`), and the content becomes the `children` prop, one child per top-level node. A dynamic attribute value, such as `title={project().name}`, is passed as a getter, the way Solid passes JSX props. Close the tag with `</{Card}>`, or self-close it with `<{Card} />`. The built-ins work the same way, called the way their signatures take children:

```python
html(t"""
  <{Show} when={user()} fallback={sign_in}>
    <p>Welcome back.</p>
  </{Show}>
  <{Theme} value="dark"><{Toolbar} /></{Theme}>
  <{Link} href="/settings" class="nav">Settings</{Link}>
""")
```

Type checkers can't see inside the template string, so the tag form's props are checked at run time in dev mode, like any component call. Use the call form when you want the checker's help.

## Templates and reactivity

A component runs once, so the template it returns is mounted once; only its slots' bindings ever update. Each dynamic expression is its own binding, so `<b title={user().role}>{user().name}</b>` updates the attribute and the text separately, with no re-run of anything else.

When a reactive *hole* returns a template, the hole re-runs when its inputs change. If it returns an instance of the same literal as before, Wybthon patches the mounted instance slot by slot instead of replacing it, the way lit-html does:

```python
def summary():
    if user().is_admin:
        return html(t"<b>{user().name} (admin)</b>")
    return html(t"<span>{user().name}</span>")


html(t"<div>{summary()}</div>")
```

Here `{summary()}` is a hole, and it re-runs when `user` changes. While the user stays an admin, it returns the same literal again and the mounted `<b>` is patched in place; when that changes, a template from the other literal replaces it.

## Templates and `h()`

[`h(tag, props, *children)`][wybthon.h] is the programmatic layer, the counterpart of Solid's `h`. Use it when markup is built by code: generated forms, recursive trees, or components that compute their tag. The two mix freely, and they share one set of prop appliers, so a prop means the same thing in both:

```python
from wybthon import h, html


def heading(level, text):
    return h(f"h{level}", {"class": "title"}, text)


html(t"<section>{heading(2, title())}{body}</section>")
h("div", {"class_": "page"}, html(t"<h1>Title</h1>"))
```

`h()` props accept Python names (`class_`, `html_for`, `aria_label`, `on_click`) as well as HTML names. The compiler only rewrites templates, so the arguments of an `h()` call are evaluated when it runs: pass an accessor or a lambda where a value should stay reactive (`h("p", None, count)`). A t-string isn't markup outside `html()`; pass it to `html()` first.

## Server rendering, hydration, and SVG

A server render, a hydrating client, and SVG or MathML content expand a template into the same VNodes `h()` would build and mount those, so output and hydration keys are identical whichever style you use. Everything else, which is every browser update after hydration, uses the compiled path.

## Editor support

Python expressions inside `{...}` are highlighted and type-checked as code. The surrounding HTML is a string, so editors don't highlight or format it unless you add an extension for HTML in t-strings, and type checkers don't check a component tag's attributes.

## See also

- [The compiler](compiler.md): what it rewrites, where it runs, and how to inspect it.
- [Components](components.md): props, children, and the run-once model.
- [Virtual DOM](vdom.md): how compiled templates mount and update.
- [`html` API reference](../api/templates.md).
