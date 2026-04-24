# Examples

Walk through focused examples that mirror the demo app pages. Each example links to a runnable file under `examples/demo/` in the repo and explains the patterns it demonstrates.

| Example | What it shows | Source |
| --- | --- | --- |
| [Counter](examples/counter.md) | Signals, derived values, and event handlers. | `examples/demo/app/pages/counter.py` |
| [Async fetch](examples/fetch.md) | [`create_resource`][wybthon.create_resource] with [`Suspense`][wybthon.Suspense] for loading states. | `examples/demo/app/pages/fetch.py` |
| [Forms](examples/forms.md) | [`form_state`][wybthon.form_state] and accessibility-friendly bindings. | `examples/demo/app/pages/forms.py` |
| [Error boundary](examples/errors.md) | Recovering from render errors with [`ErrorBoundary`][wybthon.ErrorBoundary]. | `examples/demo/app/pages/errors.py` |
| [Router](examples/router.md) | [`Route`][wybthon.Route], [`Link`][wybthon.Link], and dynamic params. | `examples/demo/app/pages/router.py` |
| [Authoring patterns](examples/authoring-patterns.md) | Common idioms for building reusable components. | `examples/demo/app/pages/authoring.py` |

!!! tip "Running the demo"

    Run `python -m http.server` from the repository root and open
    [`/examples/demo/index.html`](http://localhost:8000/examples/demo/index.html)
    to see these examples in action. The dev server (`wyb dev --dir .`)
    additionally provides hot-reload on file changes.

## Next steps

- Read the [Concepts](concepts/primitives.md) section for the underlying mental model.
- Browse the [API reference](api/wybthon.md) when you need precise function signatures.
