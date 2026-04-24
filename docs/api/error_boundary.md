### wybthon.error_boundary

::: wybthon.error_boundary

#### What's in this module

[`ErrorBoundary`][wybthon.ErrorBoundary] catches render errors in its
descendant subtree and renders a fallback in their place. Use it to
isolate failures so a single broken widget can't take down the rest of
the page.

#### Usage

```python
from wybthon import ErrorBoundary, component
from wybthon.html import button, div, p


@component
def Profile(user_id):
    raise RuntimeError("not implemented")


@component
def Page():
    return ErrorBoundary(
        fallback=lambda err, reset: div(
            p("Something went wrong: ", str(err)),
            button("Try again", on_click=lambda _e: reset()),
        ),
        children=lambda: Profile(user_id=42),
    )
```

- `fallback` receives the error and a `reset()` callback. Calling
  `reset()` clears the error and re-renders the children.
- An [`on_error`][wybthon.ErrorBoundary] hook (if provided) lets you
  send the error to your monitoring stack.

#### See also

- [Concepts → Error Boundaries](../concepts/error-boundaries.md)
- [Concepts → Suspense and Lazy Loading](../concepts/suspense-lazy.md)
- [Examples → Error Boundary](../examples/errors.md)
