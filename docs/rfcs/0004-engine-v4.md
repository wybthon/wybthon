# RFC 0004: Engine v4: the Wybthon compiler, Solid-style props, and leaner bindings

- **Status:** Implemented
- **Author:** Owen Carey
- **Created:** 2026-10-21

## Summary

Give Wybthon the one part of Solid it still lacks: a compiler. Solid's compiler does two jobs. It turns static markup into templates, which Wybthon already does at run time with t-strings (RFC 0003), and it turns every dynamic expression in the markup into a getter, so `{count() * 2}` stays reactive without the author wrapping it. Python can do the second job too. A t-string's interpolations are separate nodes in the module's syntax tree, so a small AST transform can defer each dynamic one before the module runs.

With that in place, the rest of the engine follows Solid more closely, and costs less:

1. **The compiler.** `wybthon.compiler` rewrites `html(t"...")` calls. Dynamic interpolations become getters, component calls receive getters for their props, and each literal's parse tree and mount function are emitted as ordinary Python, so a production build never parses a template or generates code at run time. It runs in `wyb build`, `wyb dev`, an import hook, and a pytest plugin.
2. **Solid-style props.** Fields are plain annotations (`title: str = "Hi"`), and `props.title` is a tracked read that returns the value. `Prop[T]` goes away.
3. **Leaner bindings and faster lists.** A binding that reads nothing reactive never allocates a computation; bindings keep their state in slots instead of closures; a list row is its own owner and allocates its index signal only when something reads it; keyed lists match unchanged and swapped runs without per-row work.
4. **Solid 2.0 RC.17 alignment.** Add `create_deferred`, `is_equal`, `is_static`, `flatten`, `lazy_module`, and `on_hydration_end`.
5. **Removals.** The element helpers (`div(...)` and friends, `wybthon.elements`, `wybthon.svg`), the runtime shape compiler, `Prop[T]`, and t-strings outside `html()`. `h()` stays as the programmatic layer.

The Virtual DOM stays as the batching layer between Python and the browser.

## Motivation

### The last gap in the mental model is the compiler

Solid's migration story is "components run once, reactivity is fine-grained, the compiler takes care of the rest." Wybthon matches the first two. For the third, the migration guide says Solid's compiler wraps expressions in effects for you, and that Python can't. That gap is the reason for most of what's unusual about writing Wybthon today:

- inline expressions must be wrapped, and Python's grammar forces parentheses: `{(lambda: count() * 2)}`. That pattern appears 50 times in the documentation and tests;
- props are accessors, so components read `props.step()` and use `props.initial.peek()` for a one-time read;
- `Prop[T]` exists only to tell the runtime which props are reactive;
- passing a prop through to a child stays reactive only if the author remembers not to call it.

Solid doesn't have any of these, because its compiler decides which expressions are dynamic. The decision is syntactic: an expression containing a call or a member access might read a signal, so it becomes a getter; anything else is a value. Python's syntax tree supports exactly the same rule, and t-strings keep their interpolations as separate nodes in it, so the decision can be made before the module runs, with no change to the language.

### Startup pays for templates twice

RFC 0003 compiles each template literal the first time it runs. Profiling that compilation natively shows where its time goes, per template:

| Phase | Native CPython |
| --- | ---: |
| Parse, normalize, and validate | 120 to 170 µs |
| Build the slot plan and skeleton | 40 to 50 µs |
| Generate the mount function (`compile` and `exec`) | 1,070 to 1,280 µs |

Generating the mount function is 85% of the cost, and every page pays it again for every template it renders, in WebAssembly, where Python runs two to three times slower. A compiler that already parses each literal can emit that function as ordinary module code, which `wyb build` turns into bytecode like the rest of the application.

### Creating and removing rows costs a few dozen objects each

The browser benchmark's update paths are fast: selecting a row among 10,000 commits in under a millisecond. Creating and clearing aren't, and the profile is flat; no function dominates. What dominates is object count. A mounted template row with a selection binding keeps 43 objects the cyclic collector tracks:

| Objects per row | Count |
| --- | ---: |
| Cells | 11 |
| Dictionaries | 8 |
| Functions | 7 |
| Tuples | 6 |
| Computations, VNodes, and handler records | 2 each |
| The row, its owner, its index signal, its projection key, a list | 1 each |

Many of those are closures: each attribute binding and each hole keeps its apply function, the cells it closes over, and the closure tuple. In Pyodide the collector's work grows with the live object count, which is why clearing 10,000 rows took 449 ms in the browser against 212 ms natively, and why RFC 0003 concluded that "further gains need cheaper reactive nodes rather than less tree work."

Keyed list matching also walks every row in Python. Swapping two rows of 10,000 calls a row update 10,000 times; natively it takes 22 ms, and 93 ms in the browser.

### Solid 2.0 kept moving

Solid 2.0 isn't stable yet; `2.0.0-rc.17` is the current release candidate. Since RC.14, which RFC 0002 aligned with, it added `createDeferred`, `isStatic`, `lazyModule`, and made `onHydrationEnd` public, and its documented exports include `isEqual` and `flatten`.

## Design

### 1. The compiler

#### What it rewrites

The compiler rewrites every call of Wybthon's `html` whose argument is a t-string literal. It resolves `html` through the module's imports (`from wybthon import html`, `from wybthon.templates import html`, an alias of either, or `wybthon.html` through `import wybthon`), so a module that defines its own `html` is left alone. Nothing else in the module changes.

#### Which expressions become getters

An interpolation's expression is **dynamic** when it contains a call, an attribute access, or a subscript, ignoring the bodies of lambdas inside it. Everything else (a name, a constant, a lambda, an f-string of names) is **static**. This is Solid's rule: a name can't change by itself, but a call or a member access can read a signal, a store, or a prop.

| Position | Dynamic expression | Static expression |
| --- | --- | --- |
| Child: `<p>{count() * 2}</p>` | A getter: a reactive hole | The value, as today |
| Attribute: `class={row_class(id)}` | A getter: a reactive binding | The value |
| Part of an attribute: `class="card {kind()}"` | A getter for that part | The value |
| Component tag attribute: `<{Card} title={user().name}>` | A getter the component reads through its props | The value |
| Spread: `<input {omit(props, "x")}>` | Evaluated once, when the template is created | The value |
| Event handler (`onclick`), `ref` | Never wrapped: handlers and refs are values | The value |
| Nested `html(t"...")` | Never wrapped: it's markup, compiled in place | |

Existing code keeps working. A signal or memo placed directly (`{count}`) is still an accessor, a lambda is still a reactive expression, and the runtime still treats both the way it does today.

**Calls in child position.** `{Show(...)}`, `{Card(title=user().name)}`, and `{badge(user())}` are all calls, but they mean different things. In JSX the difference is syntactic (`<Card>` against `badge()`); in Python it isn't, and a naming convention can't tell `Card(...)` from `Decimal(...)`. So a call whose callee is a name or a dotted name is dispatched at run time:

```python
__wybthon__.call(Card, lambda: Card(title=user().name), (), {"title": getter(lambda: user().name)})
```

- When the callee is a component (an `@component`, a lazy or dynamic component, a context, or a built-in such as `Show`, `For`, `Loading`, or `Link`), it's called with the prepared arguments: each dynamic argument is a getter, exactly what `<{Card} title={user().name}>` passes. Arguments are prepared recursively, so `Errored(Loading(...))` builds its inner component the same way.
- Any other callee (`badge`, `str`, `Decimal`) gets the deferred call back as one getter, so the whole expression is a reactive hole, which is what Solid does with a function call in JSX.

A built-in that takes a callback (`For`'s row function, `Show`'s children, a `keyed` function) unwraps a getter it receives once, untracked, so `For(rows(), make_row(kind))` behaves as it reads.

**Captured names.** A getter evaluates its expression later, possibly after a loop variable has moved on. The compiler captures every name the expression reads from an enclosing function scope, by value, when the template is created, as keyword-only defaults of the getter's lambda. Python's late binding never shows through a template, and templates in class bodies can read class-level names.

**Conversions and format specs.** `{price():.2f}` and `{name()!r}` fold into the getter, so the hole renders the formatted text.

**Expressions it doesn't wrap.** An expression containing `await`, `yield`, or an assignment expression can't move into a lambda without changing its meaning, so it stays eager.

#### Precompiled templates

The compiler parses and validates each literal with the same code `html()` uses at run time, so a malformed template is an error when the module is compiled, with the file and line. It then emits, at the top of the module:

- the literal's normalized parse tree, as a tuple of constants;
- one mount function per compiled element, as an ordinary `def` (the code `wybthon.templates` previously generated with `exec`);
- an entry object holding both, created lazily on first use.

The call becomes `html(t"...", __wybthon_t0__)`. On first use, the entry rebuilds the slot plan from the tree (no parsing, no regular expressions, no validation) and installs the precompiled mount functions. A production build never runs the template parser or `exec`.

The generated names (`__wybthon__`, `__wybthon_t0__`, `__wybthon_m0__`) are dunder names, which Python never mangles inside classes and applications don't define.

#### Where it runs

- **`wyb build` and `wyb dev`** compile application sources through the compiler before writing bytecode into the archives.
- **An import hook**, installed by `import wybthon` (or explicitly with `wybthon.compiler.install()`), compiles candidate modules imported after it. A candidate is a source file outside the standard library that mentions both `wybthon` and `html` and contains a t-string. Compiled code is cached next to the normal bytecode under its own tag (`*.opt-wyb1.pyc`), so a cached plain compile is never mistaken for a compiled one. An unchecked-hash bytecode file that `wyb build` wrote is used as is.
- **A pytest plugin** (registered through the `pytest11` entry point) compiles test modules alongside pytest's assertion rewriting, and gives their cached bytecode its own tag.
- **`wyb run script.py`** runs a script with its own templates compiled, for scripts and quick experiments.
- **Prerendering** imports the application after Wybthon, so the hook compiles it.

#### Templates that weren't compiled

`html()` still compiles a literal at run time when it's called without an entry: in a REPL, in `exec`'d code, or in a `__main__` script run directly. Such a template has already evaluated its dynamic expressions once, so in dev mode, `html()` checks each interpolation's source text (`Interpolation.expression`) and raises `TemplateError` when a dynamic expression arrived as a plain value, naming the expression and how to compile the module. Code can't silently behave differently depending on whether it was compiled.

### 2. Solid-style props

```python
from collections.abc import Callable

from wybthon import ParentProps, component, html, prop


class CardProps(ParentProps):
    title: str
    body: str = ""
    tags: list[str] = prop(default_factory=list)
    on_close: Callable[[], None] | None = None


@component
def Card(props: CardProps):
    def close():
        if props.on_close is not None:
            props.on_close()

    return html(t"""
      <div class="card">
        <h2>{props.title}</h2>
        <p>{props.body or "No details."}</p>
        {props.children}
        <button onclick={close}>Close</button>
      </div>
    """)
```

- Fields are plain annotations. `prop(default=...)` and `prop(default_factory=...)` are the field specifier for defaults that need one; ordinary defaults work as in a dataclass.
- **Reading a prop returns its value**, tracked. In a template, `{props.title}` is dynamic, so the compiler makes it a getter, and the text updates when the parent's value changes. `props.body or "No details."` is one expression and one binding.
- The parent may pass a value, a compiler getter, or an accessor. A getter is always unwrapped on read. An accessor (a signal, a memo, or a zero-argument function) is unwrapped too, unless the field's annotation is callable (`Callable[...]` or `Accessor[...]`, alone or in a union): a callback is returned as the parent passed it. For the same reason, a value field reads through an accessor a getter returns (`<{Card} title={store.title}>`, where `store.title` is a signal), as a binding of the same expression would.
- Reading a prop whose value is reactive at the top level of the component body warns in dev mode, as Solid does: the read happens once. Wrap it in `untrack(lambda: props.initial)` when a one-time read is what you want. A constant can't change, so reading one doesn't warn.
- Type checkers see `title: str`, so `{Card(title=user().name)}` is checked against the field types inside an interpolation, and the compiler still passes a getter.
- `is_static(props, "title")` reports whether the parent passed a plain value, as Solid 2.0's `isStatic` does.
- `merge(...)` and `omit(...)` return views that read like props: `view.title` is the tracked value. Spreading a view onto an element (`<div {omit(props, "title")}>`) binds each key reactively.

Patchable components (those mounted directly in a reactive hole's result, or passed to `render`) keep RFC 0003's single version signal per props instance, so reading a constant prop costs nothing anywhere else.

### 3. Leaner bindings and faster lists

**A static probe before a computation.** A hole or attribute binding first runs its expression under a lightweight observer. If the expression reads nothing reactive, creates nothing, and returns synchronously, the result is applied and no computation exists. The probe stops at the first reactive read, and the binding then runs as a computation as it does today. A probe that returns an accessor without reading anything (`{row["label"]}` returning a signal) re-targets the binding at that accessor, so a signal in a data structure still binds directly. This replaces RFC 0003's special cases for constant props.

**Bindings keep state in slots.** Attribute bindings and holes are small `Computation` subclasses that hold their node, name, and last value in slots and implement their apply stage as a method, instead of a closure with its cells.

**Rows.** A list row is its own owner and its own index accessor. Its index is a plain integer until something reads `index()` in a tracking scope, which is when the signal behind it is created.

**Handlers.** A node with one delegated handler stores it directly in the handler table, without a per-node dictionary.

**Keyed matching.** Matching a new list against the mounted rows skips the common prefix and suffix by identity without calling into each row, detects swapped ends the way Solid's `reconcileArrays` does, and only then falls back to a key table for what's left.

### 4. Solid 2.0 RC.17 alignment

| Solid 2.0 RC.17 | Wybthon |
| --- | --- |
| `createDeferred(fn, options)` | `create_deferred(fn, ...)`: an async memo that, after its first value, never holds the rest of the UI; readers keep the last value while a refetch runs |
| `isEqual(a, b)` | `is_equal(a, b)`: the default equality (`==` with an identity fast path) |
| `isStatic(props, key)` | `is_static(props, key)` |
| `flatten(children)` | `flatten(children)`: resolves nested accessors and lists to rendered values |
| `lazyModule(fn)` | `lazy_module(fn)`: a cached async import with `preload()` and `peek()` |
| `onHydrationEnd(callback)` | `on_hydration_end(callback)` |

### 5. Removals

- **The element helpers.** `div(...)`, `p(...)`, and the rest of the tag functions, `element()`, `wybthon.elements`, and `wybthon.svg` are removed. Templates are the way to write markup, and `h(tag, props, *children)` is the programmatic layer, the counterpart of Solid's `h`. A helper can't benefit from the compiler: it evaluates its arguments before Wybthon sees them.
- **The runtime shape compiler** (`wybthon._shapes`). It existed to make helper trees mount like templates. `h()` trees mount on the generic path.
- **`Prop[T]`**, `prop()` returning a `Prop`, and accessor-typed props.
- **t-strings outside `html()`.** A t-string as a child of `h()`, as a hole's result, or as an attribute value is no longer formatted implicitly. Pass it to `html()`.

## Breaking changes

| Removed or changed | Replacement |
| --- | --- |
| `Prop[T]` fields and `Prop` | Plain annotations: `title: str`; read with `props.title` |
| `props.title()` and `props.title.peek()` | `props.title`; `untrack(lambda: props.title)` for a one-time read |
| `prop(default=...)` returning a `Prop` | `prop(default=...)` / `prop(default_factory=...)` for plain fields, or an ordinary default |
| `merge(...)` / `omit(...)` attribute access returned accessors | Returns values; item access (`view["title"]`) still returns accessors for spreading |
| Element helpers: `a`, `div`, `p`, `span`, ... and `element()` | `html(t"...")`, or `h(tag, props, *children)` |
| `wybthon.elements`, `wybthon.svg` | Templates (`<svg>` works in a template), or `h()` |
| `wybthon._shapes` (internal) | Removed |
| t-string children and attribute values outside `html()` | `html(t"...")` |
| `render_template`, `template_getter` in `wybthon.vnode` | Removed |
| Dynamic interpolations were evaluated once unless wrapped in a lambda | They're getters; dev mode rejects uncompiled templates that relied on the old behavior |
| A plain function call in a template's child position ran once | It's a reactive hole, as in Solid |

## Alternatives considered

**Keep `Prop[T]` and add only the compiler.** The compiler would remove the lambdas from templates, but components would still call their props, and a prop passed through to a child would still depend on the author not calling it. Solid's props are values read through getters, and the compiler makes that possible here.

**Decide component calls by capitalization.** Simple, and it's JSX's rule, but in Python it misreads `Decimal(price())`, `Path(...)`, and any other class called in a template. Dispatching on the callee at run time costs one call and is exact.

**Evaluate `Interpolation.expression` at run time instead of compiling.** `html()` could re-evaluate each dynamic expression's source text in its caller's frame. The value has already been computed once by then, closures and comprehensions make the frame's names unreliable, and `eval` on every re-run is slow.

**Rewrite functions in `@component`.** The decorator could recompile its own function's source. It can't reach templates outside components (row functions, helpers), needs the source at run time, and has to rebuild closures.

**Keep the element helpers.** They're a pleasant programmatic API, but a helper's arguments are evaluated before the compiler or the runtime sees them, so they'd keep the old, wrap-it-yourself reactivity next to templates that don't need it. `h()` covers programmatic markup.

**Compile the reactive core to a native extension (mypyc or Cython) for Pyodide.** It may be two to four times faster, but it needs a WebAssembly wheel per Pyodide release and a larger download, and it doesn't change the API. It's worth revisiting once the engine's shape stops changing.

**Do nothing.** Wybthon stays the framework where markup needs lambdas and props need calls, and every page compiles every template in the browser.

## Drawbacks and risks

- **An import hook is global.** It's scoped narrowly: only `html()` calls on t-string literals change, standard-library modules are never read, and compiled bytecode has its own cache tag. pytest's assertion rewriting is the precedent.
- **Two compilation paths.** Compiled templates and the runtime fallback share the parser, validation, slot plan, and mount code generation; only where the result is stored differs.
- **The dynamic rule is syntactic.** `{item.name}` on a plain object becomes a getter that reads nothing; the static probe applies it without allocating a computation, so it costs a lambda.
- **Error tracebacks** point into getters the author didn't write. Each getter keeps the interpolation's source position, so the traceback names the right line.
- **Breaking every component.** Every component, document page, and test changes. Wybthon is pre-1.0 with no production users, so it's the right time.

## Testing

- **Compiler unit tests:** each position's wrapping rule; captured names in loops and comprehensions; format specs; nested templates; dispatch to components, built-ins, and plain callables; unresolved and shadowed `html`; errors with file and line; precompiled entries matching runtime compilation; the import hook's cache and candidate rules; the pytest plugin; `wyb run`; and the dev-mode error for uncompiled templates.
- **Props:** reads, tracking, defaults and factories, callable fields, getters and accessors from the parent, top-level-read warnings, patchable components, `merge`, `omit`, and `is_static`.
- **Bindings and lists:** the static probe (inert, reactive, re-targeted, async, raising), slot-based bindings through transitions and error boundaries, lazy row indices, and keyed matching for swaps, reversals, prefix and suffix edits, and duplicates.
- **RC.17 additions:** one test module each.
- **Existing suites**, ported to templates and plain props: reactivity, transitions, async, stores, boundaries, router, forms, server rendering, and hydration.
- **Browser tests** on Pyodide, with the fixture app built by `wyb build`.
- **Work gates:** `benchmarks/check_work.py` keeps one command per appended row and two per selection.
- **Benchmarks**, native and browser, against v0.38.0. Targets: at most 20 tracked objects per template row; creating rows at least 1.3 times faster; clearing 10,000 rows at least 1.5 times faster; swapping and removing in 10,000 rows at least 3 times faster natively; updates no slower; no runtime template parsing or code generation in a production build.

### Results

The [engine v4 evaluation](https://github.com/wybthon/wybthon/blob/main/benchmarks/results/engine-v4.md) measured the implementation against v0.38.0 on a heavily loaded machine, so it leads with deterministic work measures.

- **Objects:** a mounted template row keeps 20 objects the cyclic collector tracks, down from 42 (13 from 32 without a selection binding), and retains 3,856 bytes instead of 6,082.
- **Templates:** a precompiled template's first use costs about 83 µs natively instead of 1,870 µs. The browser tests check that a production build never compiles a template at run time.
- **CPU time, native, by the median of alternating rounds:**
  - creating rows: about 1.1 times faster (1.38 times by minimum without a selection binding);
  - clearing: 1.2 to 1.4 times faster;
  - swapping two rows of 10,000: 2.65 to 2.92 times faster;
  - removing the first of 10,000: 1.56 to 2.45 times faster;
  - updates: no slower.
- **Targets:** the object and production targets were met. Creation and swapping were partly met, and clearing 10,000 rows missed its 1.5 times target.
- **Plain computations:** bindings stay plain `Computation`s with one extra slot. Subclasses that held their state in slots allocated as little but created rows about 8% slower than v0.38.0, because CPython 3.14 stopped specializing the reactive core's hottest attribute reads once they saw several types.
- **Probing:** only expressions without calls are probed. Probing every getter evaluated reactive expressions twice up to their first read; a store read ends a probe at once.

## Unresolved questions

- Editor support for the HTML inside t-strings, and a `wyb check` command that type-checks component tags against their `Props` classes.
- The router's data layer, server functions, and an ASGI adapter. Server functions will need the compiler to split server code from the client bundle, so they build on this RFC.
- Whether the compiler should also hoist static `h()` trees.

## Decision

Accepted on 2026-10-21. Wybthon is pre-1.0 and has no production users yet, so the breaking changes ship without a compatibility layer.
