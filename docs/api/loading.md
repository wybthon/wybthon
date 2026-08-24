### wybthon.loading

::: wybthon.loading

#### What's in this module

[`Loading`][wybthon.Loading] renders a fallback while any async
computation read under the boundary hasn't produced its first value.
Reads that raise [`NotReadyError`][wybthon.NotReadyError] register the
computation with the boundary; once every registered computation has a
value, the children show. Revalidations don't re-trigger the boundary:
an async memo that already has a value keeps serving it
(stale-while-revalidate), so content stays visible during reloads. Use
[`is_pending`][wybthon.is_pending] to render inline refresh hints
instead.

[`LoadingList`][wybthon.LoadingList] coordinates multiple sibling
`Loading` boundaries, controlling the order their contents reveal
(`reveal_order="forwards" | "backwards" | "together"`) and which
fallbacks show while loading (`tail=None | "collapsed" | "hidden"`).
With `"forwards"` (the default) contents reveal top to bottom, each
waiting for the ones before it; `tail=None` shows every pending
fallback, `"collapsed"` shows only the next one in reveal order, and
`"hidden"` shows none.

#### Usage

```python
from wybthon import Loading, component, create_memo, create_signal, dynamic
from wybthon.html import div, p, span


@component
def UserCard(id=0):
    async def fetch_user() -> dict:
        uid = id()  # tracked; refetches when it changes
        resp = await js.fetch(f"/api/users/{uid}")
        return await resp.json()

    user = create_memo(fetch_user)
    return div(
        p("Name: ", span(dynamic(lambda: user()["name"]))),
    )


@component
def Profile():
    id_, _ = create_signal(42)
    return Loading(
        fallback=lambda: p("Loading…"),
        children=lambda: UserCard(id=id_),
    )
```

- `fallback` may be a `VNode`, a string, or a callable returning one of
  those; make it a callable so it can stay reactive too.
- The boundary waits for **all** not-ready async computations read in
  its subtree.
- Boundaries nested inside another boundary coordinate with the inner
  boundary, not with an enclosing `LoadingList`.

!!! note "Sequential vs parallel loading under `LoadingList`"
    A boundary whose content hasn't mounted yet doesn't start its async
    computations, so `reveal_order="forwards"` reveals
    sequentially-loading content as a cascade. Start the memos outside
    the boundaries (or pass them down as props) when parallel loading
    matters.

#### See also

- [Concepts → Async and Loading](../concepts/async-loading.md)
- [`create_memo`][wybthon.create_memo] (async memos)
- [`ErrorBoundary`][wybthon.ErrorBoundary]
- [Examples → Async fetch](../examples/fetch.md)
