### Async Fetch

Fetch data with `use_resource`.

```python
from wybthon.reactivity import use_resource
from wybthon import h

async def load_data():
    # TODO: sample fetch using js.fetch
    return {"message": "hello"}

res = use_resource(load_data)

def View(props):
    if res.loading.get():
        return h("div", {}, "Loading...")
    if res.error.get():
        return h("div", {}, f"Error: {res.error.get()}")
    return h("pre", {}, str(res.data.get()))
```

> TODO: Add AbortSignal usage and retry UI.
