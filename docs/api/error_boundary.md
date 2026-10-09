### wybthon.error_boundary

::: wybthon.error_boundary

#### What's in this module

[`Errored`][wybthon.Errored] installs an error handler on its owner
scope. When a descendant component body, hole, prop binding, effect, or
action raises, the boundary swaps in a fallback and leaves sibling trees
untouched. It's the recommended way to keep one broken widget from
taking down the page.

| Name | Description |
| --- | --- |
| [`Errored`][wybthon.Errored] | `Errored(children, *, fallback=None, on_error=None, reset_on=None)`. |

- `children`: a node, a zero-arg callable, or a list of either. A node
  is enough: a component inside it doesn't run until the boundary
  mounts it, so `Errored(Dashboard())` needs no lambda.
- `fallback`: a node, a string, or a callable `(err, reset) -> VNode`
  (a one-argument `(err)` or zero-argument form also works). `err` is an
  [`Accessor`][wybthon.Accessor] for the caught exception, as in
  Solid 2.0, so call `err()` to read it, or place `err` itself in a
  template as a hole. `reset()` clears the error and
  re-renders the children. Without a fallback the boundary renders
  "Something went wrong."
- `on_error`: called with the exception (send it to your monitoring).
- `reset_on`: an accessor whose change clears the current error
  automatically, for example
  [`current_path`][wybthon.router.current_path].

```python
from wybthon import Errored, component, html
from wybthon.router import current_path


def fallback(err, reset):
    return html(t"""
      <div>
        <p>Something went wrong: {err}</p>
        <button onclick={reset}>Try again</button>
      </div>
    """)


@component
def Page():
    return Errored(
        Dashboard(),
        fallback=fallback,
        on_error=report,
        reset_on=current_path,
    )
```

Async memos store an exception raised by their body and re-raise it on
read, so a failed fetch inside a `Loading` surfaces at the nearest
`Errored` too. To handle an effect's error locally instead, pass
`error=handler` to [`create_effect`][wybthon.create_effect].

#### See also

- [Loading](loading.md): the pending side of async UI
- [`action`][wybthon.action]: errors route to the boundary captured at call time
- [Concepts: Error boundaries](../concepts/error-boundaries.md)
- [Examples: Error boundary](../examples/errors.md)
