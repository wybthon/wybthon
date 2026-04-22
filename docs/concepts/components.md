### Components

Wybthon uses function components exclusively, following the SolidJS model.

> **Mental model:** A component body **runs once** during mount.  Reactivity
> happens inside *reactive holes* — zero-arg callables that you embed in
> the returned VNode tree.  See [Primitives](primitives.md#reactive-holes)
> for the full story.

#### Function components with `@component` (recommended)

The `@component` decorator lets you define components using Pythonic keyword
arguments instead of a raw props dict:

```python
from wybthon import component, div, h2

@component
def Hello(name: str = "world"):
    return h2(f"Hello, {name}!", class_name="greeting")
```

Props become regular Python parameters with type annotations and defaults.
Each parameter is a **plain value** (not a getter you call with `()`). This makes components self-documenting and enables static type checking.

**Stateless** components return a `VNode` directly:

```python
from wybthon import component, p

@component
def Greeting(name: str = "world"):
    return p(f"Hello, {name}!")
```

**Stateful** components create signals during setup and embed reactive
holes (signal getters or `dynamic(lambda: ...)`) in the returned tree.
The body runs once; only the holes update when signals change:

```python
from wybthon import button, component, create_signal, div, p, span

@component
def Counter(initial: int = 0):
    count, set_count = create_signal(initial)

    return div(
        p("Count: ", span(count.get)),                          # ← reactive hole
        button("+1", on_click=lambda e: set_count(count() + 1)),
    )
```

`count.get` is a zero-arg accessor.  When you place it in the VNode
tree, the reconciler wraps it in its own effect so only that text
node updates — the surrounding component body does not re-run.

> **Note (legacy pattern):** Components may also return a *render
> function* (`def render(): return ...`); this is treated as a
> single-root reactive hole and works identically to the example
> above for backward compatibility.  New code should prefer the
> direct return + holes style.

**Children** are received via a `children` parameter as a plain vnode, list, or `None`:

```python
from wybthon import component, h3, section

@component
def Card(title: str = "", children=None):
    kids = children or []
    if not isinstance(kids, list):
        kids = [kids]
    return section(h3(title), *kids, class_name="card")
```

**Direct calls** with keyword args return a `VNode`, so you can compose
components without `h()`:

```python
Counter(initial=5)
Card("child1", "child2", title="My Card")   # positional args become children
```

The component still works with `h()` as usual:

```python
from wybthon import h

h(Counter, {"initial": 5})
```

See: [Primitives](primitives.md) for the full signals-first API.

#### Component ownership and lifecycle

Each component instance gets a `_ComponentContext` (a subclass of
`Owner`) that participates in the reactive **ownership tree**.  This
context is the parent owner for everything created during the
component's setup phase, including the per-hole effects.

```
_ComponentContext (Counter)       ← created when Counter mounts (body runs once)
├── setup effect                  ← child of the component context (survives the body)
├── on_cleanup callback           ← registered on the component context
└── reactive holes                ← each hole has its own effect, also a child
    ├── span(count.get)           ← effect that updates one text node
    └── ...
```

**Setup effects** (created in the component body, before `return`) and
**reactive hole effects** are both owned by the `_ComponentContext`.
They are disposed when the component unmounts.

When a hole returns a sub-tree containing further effects (for
example a hole returning a VNode that contains its own holes), the
inner effects are owned by the hole's effect.  When the hole re-runs,
those inner effects are disposed first (so their `on_cleanup`
callbacks fire), then re-created on the next evaluation.

This distinction is automatic — no special API is needed.  The ownership
tree tracks which owner is active at the time `create_effect` or
`create_memo` is called.

```python
from wybthon import component, create_effect, create_signal, dynamic, li, p, ul

@component
def SearchResults(initial: str = ""):
    query, set_query = create_signal(initial)
    results, set_results = create_signal([])

    # Setup effect — runs once on mount, disposed on unmount.
    create_effect(lambda: print("query changed:", query()))

    return ul(
        # Reactive hole — its effect re-runs only when ``results`` changes.
        # When it re-runs, any inner effects are disposed and recreated.
        dynamic(lambda: [li(r) for r in results()]),
    )
```

When a component unmounts, the reconciler calls `dispose()` on its
`_ComponentContext`, which walks the tree depth-first: hole effects,
setup effects, and cleanup callbacks are all torn down automatically.

#### Traditional function components

You can still define components the traditional way with a `props` dict.
This style is fully supported and does not require a decorator:

```python
from wybthon import div, h2

def Hello(props):
    name = props.get("name", "world")
    return h2(f"Hello, {name}!", class_name="greeting")
```

The HTML helpers accept **children as positional arguments** and **props as keyword arguments**. Use `class_name` instead of `class` (reserved word in Python) and `html_for` instead of `for`.

#### Fragment

Use `Fragment` to group children without adding a visible wrapper element. The reconciler mounts children directly in the parent and uses **empty comment nodes** as start/end markers (not a `display: contents` wrapper), so fragments do not pollute the DOM or break CSS selectors that expect a certain element structure.

```python
from wybthon import Fragment, h1, p

@component
def PageContent():
    return Fragment(
        h1("Title"),
        p("Body text here."),
    )
```

#### `memo`

Wrap a function component with `memo` to skip re-renders when its props
have not changed (shallow identity comparison by default):

```python
from wybthon import component, memo, h

@component
def ExpensiveList(items=None):
    its = items or []
    return h("ul", {}, *[h("li", {}, str(i)) for i in its])

MemoList = memo(ExpensiveList)
```

Pass a custom comparison function for deeper control:

```python
MemoList = memo(ExpensiveList, are_props_equal=lambda old, new: old["items"] == new["items"])
```

#### `forward_ref`

Use `forward_ref` to create a component that can receive a `ref` prop
and forward it to a child element:

```python
from wybthon import forward_ref, h

def _render(props, ref):
    return h("input", {"type": "text", "ref": ref, "class": "fancy-input"})

FancyInput = forward_ref(_render)

# Usage: h(FancyInput, {"ref": my_ref})
```

The wrapped function receives `(props, ref)` instead of `(props,)`.
When no `ref` is provided, `ref` is `None`.

#### `create_portal`

Use `create_portal` to render children into a DOM node outside the
parent component's hierarchy — ideal for modals, tooltips, and overlays:

```python
from wybthon import component, create_portal, h

@component
def Modal():
    return h("div", {},
        h("p", {}, "Page content"),
        create_portal(
            h("div", {"class": "modal"}, "I appear in #modal-root!"),
            "#modal-root",
        ),
    )
```

The second argument is an `Element` or a CSS selector string.

#### Flow control

Wybthon provides SolidJS-style **reactive** flow control components.
Each creates its own reactive scope — only the relevant subtree
re-renders when the tracked condition or list changes.

Pass **getters** (signal accessors or lambdas) for conditions, lists,
children, and fallbacks so reads happen inside the flow control's own
scope rather than the parent's:

```python
from wybthon import Show, For, Switch, Match

# Conditional rendering — keyed scope disposes on transition
Show(when=is_logged_in,
     children=lambda: p("Welcome!"),
     fallback=lambda: p("Please log in"))

# List rendering — per-item reactive scopes (keyed by identity)
# Item and index getters are signal-backed
For(each=items,
    children=lambda item, idx: li(item(), key=idx()))

# Index-based rendering — per-index reactive scopes
# Item getter updates in place when the value at that position changes
Index(each=items,
      children=lambda item, idx: li(f"[{idx}] {item()}"))

# Multi-branch matching (reactive)
Switch(
    Match(when=lambda: status() == "loading",
          children=lambda: p("Loading...")),
    Match(when=lambda: status() == "error",
          children=lambda: p("Error!")),
    Match(when=lambda: status() == "ready",
          children=lambda: p("Ready")),
    fallback=lambda: p("Unknown"),
)
```

Plain values still work when reactivity is not needed (e.g. static
conditions evaluated in a render function).

See the guide for recommended patterns around props, state, children, cleanup, and context:

- Guide: [Authoring Patterns](../guides/authoring-patterns.md)
- Example: [Authoring Patterns Example](../examples/authoring-patterns.md)
