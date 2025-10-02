### Pyodide

Wybthon runs in the browser via Pyodide.

Key points:

- Use `micropip` to install packages when needed
- Import from `wybthon` after loading the library files into Pyodide FS (the demo does this for you)
- Interop with JS via `js` and `pyodide.ffi`

```python
import micropip
await micropip.install("wybthon")
import wybthon
```

> TODO: Add guidance on threading/event loops and async APIs in Pyodide.
