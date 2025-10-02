### Typing

The codebase uses type hints and aims for clarity over cleverness.

Guidelines:

- Prefer precise types on public APIs; avoid `Any`
- Use `Optional[...]` where values can be absent
- In Pyodide/browser interop, tolerate `Any` at boundaries but narrow types internally

> TODO: Add mypy config notes and examples from `reactivity.py` and `router.py`.
