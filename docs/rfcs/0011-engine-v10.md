# RFC 0011: Engine v10: parameters are props, and lazy branches

- **Status:** Implemented
- **Author:** Owen Carey
- **Created:** 2026-11-08

## Summary

Make a Wybthon component a plain Python function whose parameters are its props:

```python
@component
def Card(title: str, body: str = "", on_close: Callable[[], None] | None = None, children: Children = None):
    return html(t"<div><h2>{title}</h2><p>{body}</p>{children}</div>")
```

The compiler, which already rewrites templates, now rewrites every read of a component's parameter into a tracked read of the parent's current value, so a parameter behaves exactly as `props.title` did: reactive in markup, current in handlers, and reactive when passed on. The `Props` and `ParentProps` classes, `RouteProps`, `prop(default=...)`, and `key=` on components are removed. The compiler also makes the content and fallback of `Show`, `Match`, `Switch`, `Loading`, `Errored`, and `client_only` lazy, as JSX children are in Solid.

## Motivation

### Performance isn't where the gap is

Nine engine releases have taken the runtime close to what its work costs. Engine v9's core measured a write and flush at about 1.4 times a 190-line reference implementation (RFC 0009's), a profile of creating 1,000 benchmark rows is flat (61 Python calls per row, no function over about 13% of the time), and Engine v9's own core changes moved the numbers by 2% to 3%. A first visit is dominated by booting Pyodide, which server rendering, input replay, boot snapshots, and a trimmed standard library already address. The next large improvement is in how applications are written.

### Every component was two declarations

A component took one parameter annotated with a `Props` subclass:

```python
class CardProps(ParentProps):
    title: str
    body: str = ""


@component
def Card(props: CardProps):
    return html(t"<div><h2>{props.title}</h2><p>{props.body}</p>{props.children}</div>")
```

That's a class per component, a `props.` prefix on every read, and a `dataclass_transform` trick that typed each component call as constructing its props class, so a hover in an editor showed a class rather than the function. The repository had 161 props classes for its 518 components. Python already has a way to declare a function's named, typed, defaulted inputs: its parameters.

### The objection to parameters no longer holds

RFC 0002 rejected parameter-style components because the body needed accessors while callers passed values, and Python's types can't express that mapping without a plugin. RFC 0004 then added a compiler that rewrites a module's syntax tree before it runs, and RFC 0004's Solid-style props made a prop read return the value. Together they remove the objection: if the compiler turns each read of `title` in the body into a read of the prop, the body sees `title: str` as a `str` and the caller passes a `str`, so the types agree with no plugin. Vue 3.5's reactive props destructure does the same for JavaScript.

It also fixes a footgun Solid has. Destructuring Solid's props in the signature (`function Card({ title })`) reads each prop once and loses reactivity; here, parameters are the props.

### Branches were built eagerly

`Show(open_(), html(t"<p>...</p>"))` built the branch's template node, and `Show(open_(), Panel())` its component node, when the template was created, whether or not the branch ever showed, and every reopening copied that node tree. Solid evaluates a branch's JSX only when it shows. RFC 0010 left this open because recognizing the flow controls needed the compiler to resolve imports, which this change needs anyway.

### Solid 2.0 hasn't moved

npm's `next` is still `solid-js@2.0.0-rc.21` and `latest` is `1.9.18`; no stable 2.0 exists. Nothing in this RFC depends on a Solid change.

## Design

### Components

`@component` keeps its runtime type, [`Component`][wybthon.Component]. Its function's parameters declare the props:

- Positional-or-keyword, positional-only, and keyword-only parameters are props, with ordinary defaults. `prop(default_factory=list)` gives a parameter a default created once per instance; `prop(default=...)` is removed.
- A `**rest` parameter collects the props the component doesn't declare, as a reactive read-only view (the view `omit` returns), which spreads onto an element. It makes the component accept any props.
- `*args` is rejected (by the compiler, and at run time for an uncompiled function).
- A parameter annotated as callable (`Callable[...]`, `Accessor[T]`, alone or in a union with `None`) returns exactly what the parent passed; any other parameter unwraps a getter or accessor the parent passed, as fields did.
- Calls bind as Python calls do: positional arguments fill positional parameters (`Greeting("Ada")`), with Python's errors for too many arguments and multiple values. Positional arguments are no longer children.
- `children` is an ordinary parameter, annotated with the new [`Children`][wybthon.Children] type (an alias of `Any`). A tag's content, the `children` keyword, and item syntax (`Card(title="Hi")[...]`) fill it.
- Components take no `key`. Dev mode rejects one, even with `**rest`. A keyed remount is a keyed `Show`, as in Solid (`Show(doc_id(), lambda id: Doc(doc_id=id), keyed=True)`); `h(tag, {"key": ...})` still keys any node.

At run time, `Component` builds the component's props class from the function's signature on first use (`Props._wyb_from_signature`), with one descriptor per parameter, as a `Props` subclass had one per field. Everything after that is unchanged: the reconciler binds one props object per mounted component, constant props subscribe to nothing, and a patch from a re-rendering parent pushes new values into the same object. Values of undeclared props (what `**rest` reads) now go through a descriptor too, so they're tracked like declared ones. Wybthon's own built-in components keep taking a props object, through an internal `Props` subclass, since Wybthon's modules aren't compiled.

### The compiler: parameters

In a module that imports `component` from Wybthon (by any alias, or through the package), the compiler rewrites each function decorated with it whose signature has parameters:

```python
@component
def Card(title: str, body: str = "", **attrs: Any):
    """A card."""
    return html(t"<div {attrs}><h2>{title}</h2>{body}</div>")
```

becomes

```python
def Card(__wybthon_props0__, /):
    """A card."""
    attrs = __wybthon_props0__._wyb_rest()
    return html(t"<div {attrs}><h2>{__wybthon_props0__.title}</h2>{__wybthon_props0__.body}</div>")


@component
@__wybthon__.props(Card)
def Card(title: str, body: str = "", **attrs: Any):
    """A card."""
    ...
```

(and the template is then compiled as usual). The original `def` keeps the signature, with its defaults evaluated where they always were and its annotations lazy, and its body emptied; `wybthon._compiled.props` attaches the rewritten body to it, and `Component` runs that body with the props object. `inspect.signature(Card)` is the function's own.

Within the body, a load of a parameter's name becomes an attribute read on the props object, following Python's scoping: a nested function, lambda, comprehension, or class that binds the same name shadows it; decorators and defaults of nested functions are evaluated in the enclosing scope and are rewritten; annotations are left alone. Because the rewrite happens before templates are compiled, `{title}` is an attribute read and therefore dynamic, which is what makes a bare parameter reactive in markup, and the template's getter captures the props object, not the value.

Parameters are read-only. Assigning, augmented-assigning, deleting, or rebinding one in the component's own scope (by `for`, `with`, `import`, `except`, a walrus, a `match` capture, or a nested `def` or `class` of that name), or declaring one `nonlocal` in a nested function, is a `SyntaxError` at the binding: "'title' is a component parameter, which is a read-only prop; assign to a new name."

`is_static(title)` inside a component is rewritten to `is_static(<props object>, "title")`, a question about how the parent passed the prop. `is_static(view, "key")` still works for views, and `is_static(value)` outside a compiled component raises `TypeError`.

Components nested in components each get their own props name (`__wybthon_props1__`, ...), so an inner component reading an outer parameter reads the outer component's prop.

An uncompiled component with parameters (a module imported before `wybthon`, `exec` of raw source) raises `TypeError` in dev mode at its first call or mount, as an uncompiled template does; outside dev mode it runs with its props' current values, which don't update.

### The compiler: lazy branches

For a call of `Show`, `Match`, `Switch`, `Loading`, `Errored`, or `client_only` imported from Wybthon, the arguments that hold content (`Show`'s `children` and `fallback`, `Match`'s `children`, `Switch`'s `fallback`, and the `children` and `fallback` of the others, by position or keyword) become zero-argument functions when they're markup (`html(t"...")`) or a call whose callee's name is capitalized (a component). The flow controls already accepted zero-argument functions, which their regions call when a branch mounts, inside the branch's scope. Inside a template, a component call in content is first prepared as one in a child position is (`wybthon._compiled.call`), so it still receives getters for its dynamic props. Names, lambdas, and lowercase calls, which may produce callbacks (`Show(user, greeting)`), are passed as written, and captured names follow the getters' rule (captured by value when their binding can change, as in a loop).

The tag form (`<{Show} when={...}>content</{Show}>`) still builds its content when the tag is created.

### Handlers on component tags

A component tag's attribute that names a handler (`onclick`, `onClick`, `on:click`), which the compiler already passed as is rather than as a getter, now becomes the prop `on_click`: the spelling of a callback parameter (`on_click: Callable[[], None]`), and the spelling a spread binds as a delegated handler, so `<{Button} onclick={save}>` reaches a `**rest` spread on the button. Before, it arrived as `onclick` and a spread wrote it as a string attribute.

### Typing

To a type checker, `component` returns the decorated function's own type with a `Node` result (`Callable[P, Node]`), so calls are checked against the signature and messages name the component (mypy: `Unexpected keyword argument "bogus" for "Card"`). Inside the body, a parameter has its annotated type. [`Node`][wybthon.Node] declares `__getitem__` for type checkers, so item syntax on a component call checks. `wyb check` is unchanged: it shadows each component tag into a call, which is now checked against the function.

### The router

`RouteProps` is removed. A route's component declares the route props it uses as parameters, `params: dict[str, str]`, `search: SearchParams`, `data: Any`, and `children: Children`, and the router passes only those (`wybthon.component.declared_props`). A component with `**rest`, or a plain function, receives all four; a lazy component's are filtered once it loads. Extra parameters with defaults replace subclassing `RouteProps`.

### The import hook

A candidate module mentions `wybthon` and either contains a t-string with `html`, or mentions `component` or one of the six flow controls. The bytecode cache tag becomes `opt-wyb4`.

## Breaking changes

| Removed or changed | Replacement |
| --- | --- |
| `Props`, `ParentProps` (`wybthon` and `wybthon.reactivity`) | Parameters: `def Card(title: str, body: str = "", children: Children = None)` |
| `props.title` in a component | `title` |
| `wybthon.router.RouteProps` | Parameters named `params`, `search`, `data`, `children`, as the component needs |
| Subclassing `RouteProps` to add fields | Extra parameters with defaults |
| `prop(default=value)` | An ordinary default; `prop(default_factory=...)` remains |
| `key=` on a component call | A keyed `Show` for remounts, `For` for lists, or `h(Comp, {"key": ...})` |
| Positional arguments to a component were children | They bind to parameters; pass children by `children=`, item syntax, or a tag's content |
| `omit(props, "label")` to forward the rest | A `**rest` parameter (`omit` and `merge` still work on views and dicts) |
| `is_static(props, "name")` | `is_static(name)` in a compiled component |
| A component call was typed as its props class | Typed as the function, returning `Node` |
| A component with parameters ran uncompiled | Dev mode raises `TypeError`; compile the module (import it after `wybthon`, or use `wyb run`) |
| The content of `Show`, `Match`, `Switch`, `Loading`, `Errored`, and `client_only` was built when the call ran | Markup and component calls there are built when the branch shows |
| A handler attribute on a component tag (`onclick`) arrived as the prop `onclick` | It arrives as `on_click` |
| Bytecode cache tag `opt-wyb3` | `opt-wyb4` |

## Alternatives considered

**Keep `Props` classes.** They work, and they type-check, but they double every component's declarations and hide its signature from editors. The compiler that makes parameters possible already runs on every module that has templates.

**A `props` parameter typed by a `TypedDict` or `Unpack[...]`.** `def Card(**props: Unpack[CardProps])` types the call without a class per component in the body, but still needs one beside it, and the body would read `props["title"]`.

**Rewrite parameter reads at run time.** `@component` could recompile its own function. RFC 0004 rejected that for templates for the same reasons: it needs the source at run time, rebuilds closures, and can't see helpers outside the component.

**Pass getters and make the body call them (`title()`).** Solid 1's signals-as-props idea. It reads unlike Python, every parameter's type would be a lie, and passing a parameter on would need care that `title` doesn't.

**Keep `key` with a typing hack.** A `ParamSpec` can't add a keyword to a signature, so typed `key=` would need the call typed as something other than the function. Solid has no component key either; a keyed `Show` is its idiom.

**Make every call lazy, or none.** Wrapping every argument would turn a callback factory (`Show(user, make_row("kind"))`) into a function returning a callback, which the region would mount. Capitalized calls and markup are what content looks like; anything else keeps its exact meaning.

## Drawbacks and risks

- **A bare name means something different inside a component.** `title` is a tracked read, not a local. Reading one at the top of the body reads it once, as before; dev mode still warns when that freezes a reactive value.
- **Components need the compiler, as templates did.** A component in an uncompiled module raises in dev mode instead of silently losing reactivity.
- **Two functions per component.** The emptied signature function and the body share a name and line; tracebacks name the body, which is the code that ran.
- **Laziness changes when content is built.** A side effect in content markup, such as a call in an interpolation of a hidden branch, runs when the branch shows and each time it reopens, as in Solid.
- **`**rest` spreads keep the keys they mounted with**, as every spread does; values stay reactive.

## Testing

- The unit suite (3,240 tests, 82% branch coverage), including `tests/test_engine_v10.py` (the compiled form, aliases, nested components, handlers reading current props, pass-through, `is_static(param)`, `**rest` updates and `key`, every lazy flow control, content components receiving getters, loop captures, laziness outside templates, lazy route components) and a rewritten `tests/test_component.py` (positional binding, signatures, read-only parameters, shadowing, uncompiled modules, `prop()`).
- The typing fixtures under mypy and pyright, with the new `no-key` case and messages that name the component.
- `wyb check` against parameter components.
- The browser suite (95 tests in Chromium on Pyodide), including the full-stack, hydration, and production-build suites, whose apps now declare parameters.
- `benchmarks/component_bench.py`, `benchmarks/row_bench.py`, and `benchmarks/ssr_bench.py` against v0.45.0, each with the components written in the checkout's own idiom, and a hidden-branch measurement.

## Results

See [Engine v10 benchmark results](https://github.com/wybthon/wybthon/blob/main/benchmarks/results/engine-v10.md).

## Unresolved questions

- The overlay split for the reactive core, carried over from RFCs 0009 and 0010.
- Lazy content for the tag form of the flow controls.
- Spreads whose key set changes after mount.
- Claiming SVG, `select`, and raw-text templates in one command.

## Decision

Accepted on 2026-11-08. Wybthon is pre-1.0 and has no production users yet, so the changes ship without a compatibility layer.
