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

- `children`: a VNode, a zero-arg callable, or a list of either.
- `fallback`: a VNode, a string, or a callable `(error, reset) -> VNode`
  (a one-argument `(error)` or zero-argument form also works).
  `reset()` clears the error and re-renders the children. Without a
  fallback the boundary renders "Something went wrong."
- `on_error`: called with the exception (send it to your monitoring).
- `reset_on`: an accessor whose change clears the current error
  automatically, for example [`current_path`][wybthon.current_path].

```python
from wybthon import Errored, button, component, current_path, div, p

@component
def Page():
    return Errored(
        lambda: Dashboard(),
        fallback=lambda err, reset: div(
            p("Something went wrong: ", str(err)),
            button("Try again", on_click=lambda e: reset()),
        ),
        on_error=lambda err: report(err),
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
