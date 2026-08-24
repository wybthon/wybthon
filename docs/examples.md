# Examples

Walk through focused examples that mirror the demo app pages. Each example links to a runnable file under `examples/demo/` in the repo and explains the patterns it demonstrates.

| Example | What it shows | Source |
| --- | --- | --- |
| [Counter](examples/counter.md) | Signals, derived values, and event handlers. | `examples/demo/app/components/counter.py` |
| [Async fetch](examples/fetch.md) | Async [`create_memo`][wybthon.create_memo] with a [`Loading`][wybthon.Loading] boundary. | `examples/demo/app/fetch/page.py` |
| [Forms](examples/forms.md) | [`form_state`][wybthon.form_state] and accessibility-friendly bindings. | `examples/demo/app/forms/page.py` |
| [Error boundary](examples/errors.md) | Recovering from render errors with [`ErrorBoundary`][wybthon.ErrorBoundary]. | `examples/demo/app/errors/page.py` |
| [Router](examples/router.md) | [`Route`][wybthon.Route], [`Link`][wybthon.Link], and dynamic params. | `examples/demo/app/routes.py` |
| [Authoring patterns](examples/authoring-patterns.md) | Common idioms for building reusable components. | `examples/demo/app/patterns/page.py` |

!!! tip "Running the demo"

    Run `python -m http.server` from the repository root and open
    [`/examples/demo/index.html`](http://localhost:8000/examples/demo/index.html)
    to see these examples in action. The dev server (`wyb dev --dir .`)
    additionally provides hot-reload on file changes.

## Next steps

- Read the [Concepts](concepts/primitives.md) section for the underlying mental model.
- Browse the [API reference](api/wybthon.md) when you need precise function signatures.
