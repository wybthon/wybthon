### Reactivity

Signals drive the render pipeline.

```python
from wybthon import signal, computed, effect, batch

count = signal(0)
double = computed(lambda: count.get() * 2)

def log():
    print("double:", double.get())

eff = effect(log)
count.set(1)
```

- `signal(value)` → get/set
- `computed(fn)` → derived; dispose when not needed
- `effect(fn)` → runs and re-runs on dependencies
- `batch()` → batch updates and schedule once
- `use_resource(fetcher)` → async data with loading/error signals

> TODO: Explain microtask scheduling in Pyodide and fallbacks; cancellation semantics for `use_resource`.
