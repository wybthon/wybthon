# RFC 0003: Engine v3: compiled t-string templates and zero-cost components

- **Status:** Implemented
- **Author:** Owen Carey
- **Created:** 2026-10-08

## Summary

Make markup compile and make components cost nothing to mount: the two properties that define SolidJS and that Wybthon still lacks. The Virtual DOM stays as the batching layer between Python and the browser; what changes is how much Python work sits in front of it.

The change has five parts:

1. **Compiled t-string templates.** `html(t"<div class={cls}>{count}</div>")` is the primary way to write markup. Each template literal is parsed and compiled once, keyed by the identity of its static strings, and every later call only supplies the interpolated values. It's Solid's `html` tagged template, done by the language.
2. **Zero-cost components.** A prop that the parent passes as a constant costs nothing to read, a binding that reads nothing reactive is dropped after its first run, and control flow (`Show`, `For`, `Repeat`, `Switch`) mounts as native regions instead of wrapper components.
3. **A leaner reactive core.** Rarely used computation and owner fields were to move out of every instance. Measurement showed this slows every binding's hot path, so it was reverted; see [Results](#results).
4. **One props system and one in-memory DOM.** The internal `RawProps` mapping, left over from the props model RFC 0002 removed, goes away: built-in components declare typed `Props` like application components. The test suite's DOM stubs reuse `wybthon.testing`.
5. **Housekeeping.** The HTML helper module becomes `wybthon.elements`, so `wybthon.html` can be the template function. The benchmark harness builds ordinary projects instead of serving source through `/__manifest`, and duplicated helpers, dead code, and stale configuration are removed.

## Motivation

### Updates are fast; creating things isn't

Profiling the current engine (v0.37.0) on the js-framework-benchmark table and on a 237-component dashboard shows that signal-driven updates already cost 0.06 to 0.14 ms natively. Mounting is where the time goes, and the reasons are structural:

| Native CPython cost | v0.37.0 | Solid |
| --- | --- | --- |
| A component with three constant props, against the same inline `div` | 55 µs against 3.9 µs (14 times) | Components disappear at run time |
| `Show` against a raw reactive hole | 74 µs against 21 µs | `Show` is one memo |
| Building row VNodes in application code | 20 to 38% of creating 1,000 rows | Compiled away |
| Matching each instance against its compiled shape | about 20% of creating 1,000 rows | Compiled away |

The causes:

- **Every `Prop` read allocates.** Reading a `Prop[T]` field creates a `Signal`, an accessor, and, once the accessor is placed in the tree, a render computation with a two-level dependency edge. That happens even when the parent passed a plain string that can never change.
- **Control flow is built from components.** `Show` creates a component context, a `RawProps` mapping with its own signals, a truthiness memo, two owners, a branch computation, and six kernel commands.
- **Component children get a throwaway placeholder.** In a compiled shape, a component child mounts before a comment placeholder that's then disposed, so one dashboard mount sends 173 `CREATE_COMMENT` and 169 `DISPOSE` commands it doesn't need.
- **A render computation is large.** `Computation` has 39 slots and about 1 KB per binding once its closure and edges are counted. In Pyodide, live object count drives the cyclic collector, which the engine v2 evaluation identified as the dominant cost of large browser timings.

Components that cost fourteen times an element quietly push authors away from factoring their UI, which is the opposite of Solid's mental model.

### Python already has Solid's compiler

Solid's speed comes from its compiler: JSX's static structure becomes a template cloned once per instance, and only the dynamic parts run code. RFC 0002 compiled *shapes* at run time, but every instance still builds its whole VNode tree and is checked node by node against the shape before it can use the compiled mount.

[PEP 750](https://peps.python.org/pep-0750/) template strings remove both costs. A t-string literal's `strings` tuple is a constant of the code object, so it's the same object on every evaluation:

```python
def row(i, label):
    return t"<tr class={i}><td>{i}</td><td><a>{label}</a></td></tr>"

row(1, "x").strings is row(2, "y").strings  # True
```

That identity is exactly what JavaScript tagged templates provide, and what lit-html and Solid's buildless `solid-js/html` rely on. Building that t-string costs 0.36 µs; building the same row with the element helpers costs 2.84 µs, before any shape matching. The literal guarantees its own structure, so there's nothing to match.

Template strings are also the most Pythonic way to write HTML that Python has: HTML templating is the motivating example of PEP 750, and the markup reads like the HTML it produces instead of nested calls with renamed attributes (`class_`, `html_for`, `input_`).

### Two props systems

RFC 0002 replaced the props-as-mapping model with typed `Props` classes and listed `Props.raw` as removed. Every built-in component still runs on that model, renamed `RawProps`: `Show`, `For`, `Switch`, `Loading`, `Errored`, `Reveal`, `Portal`, the context provider, `dynamic`, `lazy`, the router, and virtual lists. That's a second props implementation with its own signals, and the reason built-ins are expensive.

## Design

### 1. `html()`: compiled t-string templates

```python
from wybthon import Prop, Props, Show, component, create_memo, create_signal, html


class CounterProps(Props):
    label: Prop[str]


@component
def Counter(props: CounterProps):
    count, set_count = create_signal(0)
    doubled = create_memo(lambda: count() * 2)

    def increment():
        set_count(lambda n: n + 1)

    return html(t"""
      <div class="counter">
        <p>{props.label}: {count} (doubled: {doubled})</p>
        <button onclick={increment}>+</button>
        {Show(lambda: count() > 5, html(t"<p>That's a lot of clicks.</p>"))}
      </div>
    """)
```

`html(template)` returns a node usable anywhere a node is accepted. The template is HTML with interpolations in these positions:

| Position | Example | Behavior |
| --- | --- | --- |
| Child | `<p>{value}</p>` | Same as a child of an element helper: text, a node, a list, `None`, or a reactive expression (an accessor or zero-argument function), which becomes a hole. |
| Attribute value | `<a href={url}>` | Same as an element helper prop: a static value is applied once; a reactive expression becomes its own binding. |
| Part of an attribute | `<div class="card card-{kind}">` | The parts form one string; reactive parts make the whole attribute one binding, like a t-string attribute. |
| Event | `<button onclick={handler}>` | `onclick`, `onClick`, and `on:click` all bind a delegated `click` handler. A capture suffix (`onClickCapture`) and `event(...)` options work as with helpers. |
| Spread | `<input {attrs}>` | A mapping of props applied to the element, like `**attrs` on a helper. |
| Component tag | `<{Card} title="Hi">...</{Card}>` | Calls the component with the attributes as keyword props (`class` and `for` become `class_` and `html_for`) and the content as `children`, one child per top-level node. A self-closing `<{Card} />` passes no children. Built-ins that are plain functions (`Show`, `Loading`, `Link`, context providers) are called the way their signatures take children. |

The rules follow HTML, with a few JSX conveniences:

- Attribute names are HTML names (`class`, `for`, `aria-label`, `data-id`, `tabindex`). Static values are written into the compiled markup.
- Any element may self-close (`<div />`); void elements may be written either way.
- Whitespace follows JSX: text that spans lines is trimmed line by line and joined with single spaces, and whitespace-only text containing a newline is dropped. `<pre>` keeps its text verbatim.
- Character references (`&amp;`, `&nbsp;`) are decoded in static text and attribute values.
- `<!-- comments -->` are dropped.
- `<script>`, `<style>`, and `<textarea>` take static content only.

A template with several top-level nodes returns a fragment. A template with no elements (`html(t"Hello, {name}!")`) is text and holes.

**Compilation.** The first call with a given `strings` tuple parses the template into a small tree, validates it, and compiles it:

- the static skeleton, serialized once and registered with the kernel as a native `<template>`;
- the pre-order offset of every dynamic slot, with its kind (attribute, event, ref, spread, child, component);
- the delegated event types per offset, so cloning marks listeners natively, as in RFC 0002.

Compiled templates are cached in a dictionary keyed by the `strings` object's identity (holding a reference so the identity can't be reused), with a structural fallback for templates built by hand. Templates are code, so the cache is bounded by the size of the program.

**Mounting** takes one `CLONE` command, as a compiled shape does today, then walks the slot plan with the instance's values. No VNode tree is built for static parts, and there are no per-node guards: the literal is the guarantee.

- A child slot keeps its placeholder as a permanent anchor. A text value is written into the clone command itself when the placeholder is a text node, so a row's label costs no extra command. A node is mounted in front of the placeholder, and nothing is disposed.
- Attribute, event, and ref slots use the same appliers as element helpers, so semantics can't drift between the two authoring styles.

**Re-rendering.** When a hole returns a template from the same literal again, the instance is patched slot by slot, comparing each value with the previous one by identity, as lit-html does. A changed text is one `nodeValue` write; an unchanged slot costs one comparison.

**Validation.** The compiler rejects markup the browser's parser would rewrite, with an error that names the template and the fix, rather than silently falling back: an unclosed or mismatched tag, `<tr>` directly inside `<table>` (add `<tbody>`), block content inside `<p>`, interactive content nested in itself (`<a>` inside `<a>`), interpolation inside raw-text elements, and attribute names that aren't valid identifiers for a component tag.

**Other renderers.** Server rendering, hydration, SVG, and MathML expand a compiled template into ordinary VNodes and mount those, so their output is identical to the element helpers'. A template containing `<svg>` or `<math>` always expands; its children still benefit from compilation elsewhere.

**Typing.** Interpolations are ordinary Python expressions, so pyright and mypy check them. Calling a component inside an interpolation (`{Card(title="Hi")}`) keeps full prop checking. The `<{Card}>` tag form is checked at run time in dev mode, like any component call, and is meant for passing nested markup as children.

**Element helpers stay.** `div(...)`, `h(...)`, and `element(...)` remain the programmatic layer, the counterpart of Solid's `h`. They keep RFC 0002's runtime shape compilation. They move from `wybthon.html` to `wybthon.elements` and are still exported from `wybthon`.

### 2. Zero-cost components

**Constant props cost nothing.** A component can only receive new props when a hole re-renders a tree that contains it. Components mounted anywhere else (another component's output, a list row, a `Show` branch, the inside of a template) are never patched. The renderer records which case applies when it mounts a component:

- A **patchable** component's `Prop` reads track one version signal per props instance, created on the first tracked read. A patch that changes any reactive field bumps it. That replaces one signal per field.
- A **fixed** component's `Prop` reads track nothing for a constant value. A value that's an accessor or zero-argument function is still called, so the reader subscribes to it directly.

**Inert bindings are dropped.** When a hole or reactive attribute binding finishes its first run without reading a reactive source, and without creating children, cleanups, or async work, it can never run again. The renderer disposes it immediately and keeps only the DOM it produced. Together with constant props, a component whose props never change costs about what its markup costs.

**Native control flow.** `Show`, `For`, `Repeat`, and `Switch` return region nodes the reconciler mounts directly. There's no component context, props object, or truthiness memo. (`client_only`, `NoHydration`, and `dynamic` need an owner at mount time, so they stay components, with typed internal `Props`.)

- `Show` and `Switch` are one branch computation that re-mounts only when the selected branch changes.
- When a hole re-renders a region of the same kind, the new condition or source is pushed into the mounted region instead of remounting it. That's the only part that was ever reactive.

**No throwaway placeholders.** In compiled helper shapes, a component child with a static node after it mounts in front of that node; only a component followed by another dynamic child keeps a placeholder.

### 3. A leaner reactive core

The plan was for `Computation` and `Owner` to keep their hot fields as slots, and to move the fields most instances never set to class defaults, stored per instance only when written:

- **`Computation`:** the error handler, laziness, the unobserved callback, the name, preparation owners, the readiness signal, the publication and landing transitions, the apply cleanup and apply owner, and the deferral and eager flags.
- **`Owner`:** async tasks, the context map, and the error handler.

It was implemented and reverted. It cut a computation from 328 to 216 bytes, but CPython 3.14 doesn't specialize attribute reads that fall back to a class default on these instances, which keep a `__dict__` slot. Reading one of those fields was 3.5 times slower than reading a slot, and every apply, settle, child attachment, and disposal reads several of them. Every field stays a slot. The bindings that this RFC removes outright (constant props, inert bindings, control-flow wrappers) save far more memory than the slimming did.

### 4. One props system, one in-memory DOM

`RawProps` is removed. Built-in components (`Loading`, `Reveal`, `Errored`, `Portal`, the context provider, `dynamic`, `lazy`, the router, and virtual lists) declare internal `Props` classes. An internal class can accept undeclared keys, for components that forward attributes (`Link`) or props (`dynamic`).

A non-component callable used as a tag (`h(fn, props)`) receives the props dictionary unchanged. A function that wants typed, reactive props uses `@component`.

`tests/conftest.py` builds on `wybthon.testing`'s DOM instead of carrying a copy, and the void-element and raw-text sets live in one module.

### 5. Typed control flow

`For` and `Show` get generic overloads, so callbacks are checked (`Repeat` takes an `(int) -> node` callback):

- `For(todos, lambda todo, i: ...)` infers `todo: Todo` and `i: Accessor[int]` with the default matching.
- With `keyed=False`, it infers `todo: Accessor[Todo]` and `i: int`.
- With a key function, both are accessors.
- `Show(user, lambda u: ...)` infers `u: Accessor[User]`.

### 6. Housekeeping

- `wybthon.html` (the element helper module) becomes `wybthon.elements`. `wybthon.html` is the template function.
- `wyb build` inlines the manifest into the page and emits `modulepreload` and `preload` hints for Pyodide and both source archives, so they download while the page parses instead of after the bootstrap has fetched the manifest.
- An `@action` can be an event handler directly: its wrapped function decides whether it receives the event.
- `wybthon._template` (RFC 0002's shape compiler) becomes `wybthon._shapes`.
- The browser benchmarks build the benchmark app with `wyb build` and serve its `dist`, like `compare_startup.py` already does. `benchmarks/_serve.py` and its `/__manifest` endpoint are removed.
- `DEV_MODE` leaves `wybthon._warnings.__all__`, and `is_dev_mode()` is the only reader.
- Two class-name normalizers become one.
- Dead functions, unused `noqa` directives, and stale configuration are removed:
  - the functions are `_nearest_component`, `_accessor_of`, and the shape-kind constants;
  - the configuration is the `per-file-ignores` entries for directories that don't exist, and the one-entry CI matrix.
- The documentation and examples move to templates. Examples drop lambdas the runtime never needed: boundaries take nodes, handlers take no event, and store lists are passed directly.

## Breaking changes

| Removed or changed | Replacement |
| --- | --- |
| `wybthon.html` module (element helpers) | `wybthon.elements`; the helpers are still exported from `wybthon` |
| `wybthon.html` attribute | Now the template function: `from wybthon import html` |
| `RawProps` (internal) | Typed `Props` classes |
| A plain function used as a component tag received `RawProps` | A function whose only parameter is the props receives the props dictionary, and is re-run when patched with changed props; use `@component` for typed props |
| A hole that re-renders `Show`, `For`, `Repeat`, or `Switch` patched a wrapper component | The region is patched in place; only its condition or source updates, as before |
| `wybthon._template` (internal) | `wybthon._shapes` |
| `benchmarks/_serve.py` and `/__manifest` | Benchmarks build each checkout with `wyb build` |
| `DEV_MODE` in `wybthon._warnings.__all__` | `is_dev_mode()` |

Patchable and fixed components behave identically for every prop that's passed as an accessor or that changes through a patch; the difference is only in what's allocated.

## Alternatives considered

**A build-time AST compiler for element helpers.** Deferred again. It would let `div(...)` trees skip VNode construction too. But it must prove that `div` is the helper and not a local name, it needs the same transform in tests, the dev server, and the build, and code would behave differently depending on whether it was transformed. T-strings give the same compile-once property with a guarantee from the language, and no transform.

**Templates as the only markup syntax.** Rejected. The helpers are a good programmatic API, many Python developers prefer call-style markup (htpy, FastHTML), and the runtime shape compiler already makes them reasonably fast. Two styles share one set of prop appliers, so their semantics can't drift.

**Typed component tags in templates.** Not possible without a type checker plugin: checkers don't see inside template strings. Component calls inside interpolations remain fully typed, and dev mode validates tag-form props at run time.

**Remounting patched components instead of tracking a version signal.** Simpler, but it would discard component state whenever a re-rendering hole passes a changed constant. The version signal keeps today's semantics and costs one signal per patchable instance, allocated only when it's read.

**A separate, minimal render-binding class.** Considered for the reactive core. The scheduler, transitions, and error routing all operate on `Computation`, so a second node type would duplicate their protocol. Moving rare fields out gets most of the memory benefit without a second implementation.

**Do nothing.** Components stay fourteen times the cost of their markup, and markup stays nested calls with renamed attributes.

## Drawbacks and risks

- Templates put markup in strings. Editors don't highlight HTML inside t-strings by default, and formatters don't format it. Python expressions inside interpolations are highlighted and checked as code.
- Two authoring styles exist. The documentation leads with templates and presents helpers as the programmatic layer.
- The patchable/fixed distinction depends on the reconciler knowing where a component mounts. A component mounted somewhere new that can be patched, without being marked patchable, would miss prop updates. Tests cover every mount path: hole results, `render` into an existing root, template slots, rows, branches, and boundaries.
- Dropping inert bindings relies on the computation's dependency set after its first run. A binding that reads a non-reactive global and expected to re-run never did, so nothing changes.
- The template compiler is new parsing code. Its error paths and HTML edge cases (void elements, raw text, entities, whitespace, tables) need direct tests.

## Testing

- **Unit tests:**
  - template parsing, compilation, caching, and every validation error;
  - every interpolation position, multi-root and text-only templates, and component tags with and without children;
  - slot-wise patching through re-rendering holes;
  - mixing templates with helpers, and templates inside `For`, `Show`, `Loading`, and `Errored`;
  - server rendering and hydration of templates;
  - patchable and fixed components, inert binding disposal, native regions patched by holes, typed control-flow overloads (in the typing fixtures), and teardown with no leaked handlers or bindings.
- **Existing suites:** reactivity, transitions, async, stores, boundaries, router, forms, server rendering, and hydration pass, ported to the renamed modules.
- **Browser tests:** the Playwright suite runs against the fixture project, with template-based pages added.
- **Work gates:** `benchmarks/check_work.py` keeps one command per appended row, gates a template row at one command, and gates `Show` at two commands per toggle.
- **Benchmarks:** native and browser comparisons against v0.37.0. Targets:
  - creating rows with templates at least 1.8 times faster;
  - mounting a component tree at least 2 times faster;
  - `Show` within 1.5 times the cost of a raw hole;
  - retained memory per binding lower;
  - updates no slower.

### Results

The [engine v3 evaluation](https://github.com/wybthon/wybthon/blob/main/benchmarks/results/engine-v3.md) measured the implementation against v0.37.0. The machine was under heavy unrelated load, so it leads with deterministic work measures and reports process CPU time from alternating runs.

- **Template rows** run 44% fewer function calls than helper rows and send one command per row. By CPU time they create rows 1.25 to 1.39 times faster than v0.37.0's helper rows, short of the 1.8 times target.
- **Constant props are free.** Mounting 100 components with three constant props runs a third fewer calls and creates no signals or computations, where v0.37.0 created 300 of each.
- **`Show`** runs 42% fewer calls and costs about 1.5 times a raw hole, meeting that target.
- **The dashboard** (237 component instances in v0.37.0) mounts 1.24 times faster and unmounts 1.27 times faster. It creates 1 signal instead of 407 and 350 computations instead of 554, and sends 692 commands instead of 799. That's short of the 2 times target.
- **Memory:** a helper row retains 23% less memory. A template row with a selection binding retains 3% more than a sealed helper row, because it keeps its values for slot patching.
- **Updates** are no slower.
- **The leaner reactive core (part 3) was reverted.** Moving rare fields to class defaults made a computation 112 bytes smaller, but slot-free reads of those fields aren't specialized by CPython 3.14 and were 3.5 times slower on every binding's hot path.
- **Validation:**
  - 785 unit tests pass with 87% branch coverage, including typing contracts under mypy and pyright.
  - 79 browser tests pass on Pyodide, eight of them for templates in the real HTML parser.

The largest remaining costs per row are now one object each: the row's owner and index signal, the label's computation, and the delegated handler records. Further gains need cheaper reactive nodes rather than less tree work.

## Unresolved questions

- Head management (`Title`, `Meta`, `useHead`), server functions, an ASGI adapter, and a router data layer (`query`, `revalidate`, URL-bound actions). They belong to a full-stack RFC built on this engine.
- Editor support for HTML inside t-strings (highlighting and completion), and a `wyb check` command that validates component tags against their `Props` classes statically.
- Whether a future build step should precompile template skeletons into the production bundle, removing the first-call parse.

## Decision

Accepted on 2026-10-08. Wybthon is pre-1.0 and has no production users yet, so the breaking changes ship without a compatibility layer.
