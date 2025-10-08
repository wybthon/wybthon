### Async Fetch

Fetch data with `use_resource`.

```python
from wybthon import Suspense, h
from wybthon.reactivity import use_resource

async def load_data(signal=None):
    # e.g., using js.fetch with AbortSignal
    return {"message": "hello"}

res = use_resource(load_data)

def Content(props):
    if res.error.get():
        return h("div", {}, f"Error: {res.error.get()}")
    return h("pre", {}, str(res.data.get()))

View = lambda props: h(
    Suspense,
    {"resource": res, "fallback": h("div", {}, "Loading..."), "keep_previous": True},
    Content({}),
)
```
