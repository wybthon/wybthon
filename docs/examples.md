# Examples

Walk through focused examples of the framework's core features. Each page is a self-contained walkthrough with runnable code and an explanation of the patterns it demonstrates.

| Example | What it shows |
| --- | --- |
| [Counter](examples/counter.md) | Signals, derived values, and event handlers. |
| [Async fetch](examples/fetch.md) | Async [`create_memo`][wybthon.create_memo] with a [`Loading`][wybthon.Loading] boundary. |
| [Forms](examples/forms.md) | [`form_state`][wybthon.form_state] and accessibility-friendly bindings. |
| [Error boundary](examples/errors.md) | Recovering from render errors with [`ErrorBoundary`][wybthon.ErrorBoundary]. |
| [Router](examples/router.md) | [`Route`][wybthon.Route], [`Link`][wybthon.Link], and dynamic params. |
| [Authoring patterns](examples/authoring-patterns.md) | Common idioms for building reusable components. |

!!! tip "Complete apps"

    For full applications that put these patterns together, see the
    [demo apps guide](guides/demo-app.md): standalone repositories like
    [demo-template](https://github.com/wybthon/demo-template) and
    [data-lab](https://github.com/wybthon/data-lab) that run entirely
    in the browser.

## Next steps

- Read the [Concepts](concepts/primitives.md) section for the underlying mental model.
- Browse the [API reference](api/wybthon.md) when you need precise function signatures.
