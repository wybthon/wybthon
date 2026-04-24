### wybthon.suspense

::: wybthon.suspense

#### What's in this module

[`Suspense`][wybthon.Suspense] renders a fallback while any
[`create_resource`][wybthon.create_resource] in its subtree is pending.
It's the canonical way to coordinate loading states for async data and
lazy components.

#### Usage

```python
from wybthon import Suspense, component, create_resource, create_signal
from wybthon.html import div, p, span


async def fetch_user(id_: int) -> dict:
    ...


@component
def UserCard(id):
    user = create_resource(id, fetch_user)
    return div(
        p("Name: ", span(lambda: user()["name"])),
    )


@component
def Profile():
    id_, _ = create_signal(42)
    return Suspense(
        fallback=lambda: p("Loading…"),
        children=lambda: UserCard(id=id_),
    )
```

- `fallback` is a callable so it can stay reactive too.
- The boundary waits for **all** pending resources in its subtree.

#### See also

- [Concepts → Suspense and Lazy Loading](../concepts/suspense-lazy.md)
- [`create_resource`][wybthon.create_resource]
- [`ErrorBoundary`][wybthon.ErrorBoundary]
- [Examples → Async fetch](../examples/fetch.md)
