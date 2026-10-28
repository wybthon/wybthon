# The compiler

Wybthon's compiler is the step that makes `{count() * 2}` reactive without a lambda around it. It rewrites every `html(t"...")` call in a module before the module runs, the way Solid's compiler rewrites JSX. This page explains what it changes, where it runs, how to see what it did, and where its rule stops. You don't need any of it to write components, but it's what to read when a template doesn't behave as you expect.

## What Solid's compiler does, and what Wybthon's does

Solid's compiler does two jobs with JSX:

1. It turns the static markup into a `<template>` that the browser clones per instance.
2. It turns every dynamic expression in the markup into a getter, so `{count() * 2}` re-runs when `count` changes, and a component receives its props as getters it reads later.

Wybthon does both for [`html`][wybthon.html] templates. A [PEP 750](https://peps.python.org/pep-0750/) t-string keeps each interpolation as a separate node in the module's syntax tree, so a small transform over Python's `ast` can make the same decisions before the module runs. There's no new syntax and no change to the language: the source you write is ordinary Python 3.14.

```python
@component
def Counter(props: CounterProps):
    count, set_count = create_signal(0)
    return html(t"<p>{count()} doubled is {count() * 2}, step {props.step}</p>")
```

compiles to, roughly:

```python
@component
def Counter(props: CounterProps):
    count, set_count = create_signal(0)
    # The literal's parse tree and mount function were built at compile time.
    return __wybthon_t0__.render((lambda: count(), lambda: count() * 2, lambda: props.step))
```

Each deferred expression is a slot's binding: the renderer runs it as its own computation and updates only that text node when what it read changes. The component body still runs once. The compiled call hands the literal's entry a tuple of values, one per interpolation, so no t-string is built when the template is instantiated.

## The rule: dynamic or static

An interpolation is **dynamic** when its expression contains a call, an attribute access, or a subscript, not counting the bodies of lambdas inside it. Everything else (a name, a constant, a lambda, an f-string of names) is **static**. This is Solid's rule: a name can't change by itself, but a call or a member access can read a signal, a store, or a prop.

What a dynamic expression becomes depends on where it sits:

| Position | Example | A dynamic expression becomes |
| --- | --- | --- |
| Child | `<p>{count() * 2}</p>` | A getter: a reactive hole. |
| Call in a child position | `{Show(count() > 5, ...)}` | A component built with getters, or a reactive hole; see [Calls in a child position](#calls-in-a-child-position). |
| Attribute | `<li class={row_class(id)}>` | A getter: a reactive binding. |
| Part of an attribute | `<div class="card {kind()}">` | A getter for that part; the parts render as one string. |
| Component tag attribute | `<{Card} title={user().name}>` | A getter, which the component reads through `props.title`. |
| Event handler | `onclick={make_handler(id)}` | Nothing: it's evaluated once. Handlers are values. |
| `ref` | `<input ref={refs[i]}>` | Nothing: it's evaluated once. |
| Spread | `<input {omit(props, "label")}>` | Nothing: it's evaluated once, when the template is created. |
| The component in a tag | `<{views["card"]}>` | Nothing: it's evaluated once. |
| Nested template | `{html(t"<b>{name()}</b>")}` | Nothing: it's markup, compiled in place with its own getters. |

On a component tag, an attribute named like a handler (`on_close`, `onClose`) or `ref` is passed as is too.

A static expression keeps its run-time meaning. A signal or memo placed directly (`{count}`) is an accessor, so it's bound reactively; a lambda (`{(lambda: count() * 2)}`) is a reactive expression; any other value is applied once. Both `{count}` and `{count()}` update when `count` changes.

The rule is syntactic, so it errs on the side of deferring. `{item.name}` on a plain object becomes a getter that reads nothing reactive. That costs almost nothing: before allocating a computation, the renderer runs such an expression once under a lightweight probe, and when it reads nothing reactive the value is applied and no computation exists. A getter whose value is itself an accessor (`{row["label"]}` returning a signal) binds to that accessor directly.

## Calls in a child position

`{Show(...)}`, `{Card(title=user().name)}`, and `{badge(user())}` are all calls, but they mean different things. In JSX the difference is syntactic (`<Card>` against `badge()`); in Python it isn't, and a naming convention can't tell `Card(...)` from `Decimal(...)`. So a call in a child position whose callee is a name (`Card`), or a dotted name ending in a capitalized attribute (`ui.Card`), is dispatched when the template is created:

```python
{Card(title=user().name)}
# compiles to
__wybthon__.call(Card, lambda: Card(title=user().name), lambda: Card(title=__wybthon__.getter(lambda: user().name)))
```

- When the callee is a component, it's called with the prepared arguments: each dynamic argument is a getter, exactly what `<{Card} title={user().name}>` passes. Components are `@component` functions, [`lazy`][wybthon.lazy] and [`dynamic`][wybthon.dynamic] components, contexts, and the built-ins that render markup ([`Show`][wybthon.Show], [`For`][wybthon.For], [`Repeat`][wybthon.Repeat], [`Switch`][wybthon.Switch], [`Loading`][wybthon.Loading], [`Errored`][wybthon.Errored], [`Portal`][wybthon.Portal], `Link`, and the rest). Arguments are prepared recursively, so `Errored(Loading(...))` builds its inner component the same way, and handler-named keywords (`on_close=...`) and `ref` are passed as they are.
- Any other callee (`badge`, `str`, `Decimal`) gets the deferred call: the whole call becomes one reactive hole, which is what Solid does with a function call in JSX.

A built-in that takes a callback (`For`'s row function, `Show`'s children, a `keyed` function) unwraps a getter it receives once, untracked, so `{For(rows(), make_row(kind))}` behaves as it reads.

A method call (`{item.upper()}`) isn't a component, and a call with no arguments (`{Header()}`) has no props to prepare, so both are ordinary dynamic expressions: a hole that makes the call.

## Captured names

A getter runs later, possibly after a loop variable has moved on. So the compiler captures, by value, every name the expression reads from an enclosing function scope whose binding can change: loop and comprehension variables, names assigned more than once or with `+=` or `:=`, and `nonlocal` names. They become keyword-only defaults of the getter's lambda:

```python
def rows(items):
    out = []
    for item in items:
        out.append(html(t"<li>{item.name}</li>"))  # the getter is `lambda *, item=item: item.name`
    return out
```

Each row reads its own `item`, so Python's late binding never shows through a template. A name bound once is read through its closure as usual, and templates in class bodies can read class-level names.

## Conversions and format specs

`{price():.2f}` and `{name()!r}` fold into the getter, so the hole renders the formatted text and re-formats it when the value changes. A static value with a format spec is formatted once.

## Precompiled templates

The compiler parses and validates each literal with the same code `html()` uses at run time, so a malformed template is an error when the module is compiled, with the file and line:

```text
  File "app/views.py", line 5
    return html(t"<i>{count()} <input {attrs}>")
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
SyntaxError: Unclosed tag <i>
  in template: t'<i>{...} <input {...}>'
```

It then writes three things at the top of the module:

- the literal's normalized parse tree, as a tuple of constants;
- one mount function per element (`__wybthon_m0__`, ...), as an ordinary `def`;
- an entry (`__wybthon_t0__ = __wybthon__.template(...)`) holding both, which does its work on first use.

The call becomes `__wybthon_t0__.render((value, ...))`, with each interpolation's value (or getter) in order and any conversion or format spec already applied, so a compiled template never builds a `Template` or calls `html()` at run time. On first use, the entry rebuilds the template's slot plan from the tree and installs the mount functions. A precompiled template therefore skips everything [`html`][wybthon.html] does for an uncompiled literal: tokenizing the markup, validating it against the HTML parser's rules, and generating each mount function with `compile` and `exec`. Each mount function also knows which slots always hold a getter the compiler made, and binds those without first checking what kind of value they hold. When the build's Python version matches the Pyodide runtime's, `wyb build` also ships every compiled module as bytecode, so the browser doesn't compile the Python source either; see [Deployment](../guides/deployment.md#bytecode). With `bytecode = false`, the import hook compiles each module once, as the page imports it. The [engine v4 evaluation](https://github.com/wybthon/wybthon/blob/main/benchmarks/results/engine-v4.md) measures the difference.

The generated names (`__wybthon__`, `__wybthon_t0__`, `__wybthon_m0__`) are dunder names, which Python never mangles inside classes and applications don't define.

## Where it runs

You don't call the compiler yourself. It runs in each place Python code enters a Wybthon application:

- **`wyb build` and `wyb dev`** run every application module through the compiler, which also checks every template, and write the compiled bytecode into the archives when the build's Python version matches the runtime's. The import hook uses that bytecode as is, so such a page never compiles anything.
- **The import hook.** `import wybthon` installs it, and it compiles candidate modules imported after that: source files outside the standard library that mention `wybthon` and `html` and contain a t-string. Everything else loads exactly as it would without the hook. Compiled code is cached next to the normal bytecode under its own tag (`views.cpython-314.opt-wyb2.pyc`), so a plain compile cached earlier is never mistaken for a compiled one. [`wybthon.compiler.install()`][wybthon.compiler.install] and [`uninstall()`][wybthon.compiler.uninstall] add and remove it explicitly.
- **The pytest plugin.** Installing Wybthon registers a `pytest11` plugin that compiles test modules and `conftest.py` files alongside pytest's assertion rewriting, so templates in tests behave exactly as they do in the application. Disable it with `-p no:wybthon`.
- **`wyb run script.py`** runs a script with its own templates compiled and the hook installed, for scripts and quick experiments. Arguments after the script are passed to it.
- **Prerendering** imports the application after Wybthon, so the hook compiles it.

For code you build at run time, [`wybthon.compiler.compile_source(source, filename)`][wybthon.compiler.compile_source] returns a code object with the templates compiled, ready for `exec`.

## Templates that weren't compiled

`html()` still works on a template that reaches it uncompiled: it compiles the literal itself on its first call. But by then Python has already evaluated each interpolation once, so `{count() * 2}` arrived as a number and would never update. In dev mode, `html()` checks each interpolation's source text and raises [`TemplateError`][wybthon.TemplateError] when an expression the compiler would have deferred arrived as a plain value:

```text
wybthon.templates.TemplateError: {count() * 2} was evaluated once instead of becoming
reactive, because this template wasn't compiled. Templates compile automatically in
modules imported after wybthon, in wyb build and wyb dev, and under pytest; run a
script with `wyb run script.py`, or wrap the expression in a lambda.
  in template: t'<p>{...}</p>'
```

The usual causes, and their fixes:

- **A script run with `python script.py`.** The `__main__` module is compiled by Python before Wybthon is imported. Run it with `wyb run script.py`, or move its components into a module the script imports.
- **A module that was already loading when Wybthon was first imported.** The hook only sees modules imported after `import wybthon` has run, so the module whose own `from wybthon import ...` line is the first import of Wybthon isn't compiled. Import `wybthon` first, for example in your package's entry point.
- **The REPL, `exec`, and `eval`.** Compile the source with `compile_source` before executing it, or write `{(lambda: count() * 2)}`, which is reactive with or without the compiler.
- **A t-string that isn't written in the `html()` call.** The compiler only rewrites `html(t"...")` where the argument is the literal itself. `tpl = t"..."; html(tpl)` isn't compiled; write the literal in the call.

Production builds turn dev mode off, but they compile every module, so the check has nothing to catch there.

## Inspecting what it did

[`wybthon.compiler.transform`][wybthon.compiler.transform] is the compiler's entry point: it takes a module's syntax tree and rewrites it in place. Print the result to see the generated header and the rewritten calls. Each `html(t"...")` call becomes a `render` call at the same position, whose tuple holds one value per interpolation, so pairing them with the source shows what each interpolation became:

```python
import ast

from wybthon.compiler import transform

source = """
from wybthon import Show, html

def view(count, kind, price, items):
    rows = [html(t"<li>{item.name}</li>") for item in items]
    return html(t"<p class={kind()}>{count()} {count} {price():.2f} {Show(count() > 5, rows)}</p>")
"""

written = {
    (node.lineno, node.col_offset): [item.str for item in node.args[0].values if isinstance(item, ast.Interpolation)]
    for node in ast.walk(ast.parse(source))
    if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.TemplateStr)
}
tree = transform(ast.parse(source))
print(ast.unparse(tree))
for node in ast.walk(tree):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "render":
        for text, value in zip(written[(node.lineno, node.col_offset)], node.args[0].elts):
            print(f"{{{text}}}  ->  {ast.unparse(value)}")
```

The module now starts with `import wybthon._compiled as __wybthon__`, followed by each template's mount functions and its entry:

```python
__wybthon_t0__ = __wybthon__.template(("<li>", "</li>"), ((0, "li", (), ((2, 0),)),), (__wybthon_m0__,), (0,), (0,))
```

The entry's arguments are the literal's static strings, its parse tree, its mount functions, the slots whose expressions make no calls (the ones the renderer probes before allocating a computation), and the slots that always hold a getter the compiler made. The interpolations print as:

```text
{kind()}  ->  lambda: kind()
{count()}  ->  lambda: count()
{count}  ->  count
{price()}  ->  lambda: __wybthon__.fmt(price(), None, f'.2f')
{Show(count() > 5, rows)}  ->  __wybthon__.call(Show, lambda: Show(count() > 5, rows), lambda: Show(__wybthon__.getter(lambda: count() > 5), rows))
{item.name}  ->  lambda *, item=item: item.name
```

`{price():.2f}` prints as `{price()}` because the format spec is part of the getter now.

## Limitations

- **A call's callee is evaluated when the template is created.** `{Card(...)}` looks up `Card` once, and the choice between building a component and making a hole is made then. To choose a component reactively, use [`dynamic`][wybthon.dynamic].
- **`await`, `yield`, and assignment expressions stay eager.** Moving `{await load()}` or `{(n := count())}` into a lambda would change what it means, so the compiler leaves it alone and it's evaluated once.
- **Type checkers don't see inside the markup.** The HTML around the interpolations is a string, so a tag's attributes (`<{Card} title={...}>`) aren't checked statically; dev mode checks them at run time. The interpolated expressions are ordinary Python and are checked: `{Card(title=user().name)}` is checked against `Card`'s props, and the checker sees `title` as a `str` even though the compiler passes a getter. Use the call form when you want the checker's help.
- **Tracebacks point into getters you didn't write.** Each getter keeps its interpolation's source position, so the traceback names the right file and line.

## Next steps

- Read [Templates](templates.md) for the markup syntax.
- Read [Components](components.md) for how props read the getters the compiler passes.
- Read [Testing](../guides/testing.md) for templates under pytest.
- Browse the [`wybthon.compiler`](../api/compiler.md) API reference.
- Read [RFC 0004](../rfcs/0004-engine-v4.md) for the design and the alternatives considered.
