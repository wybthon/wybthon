# Examples

Walk through focused examples of the framework's core features. Each page is a complete module you can drop into a Pyodide page (or a test) and an explanation of the patterns it demonstrates.

| Example | What it shows |
| --- | --- |
| [Counter](examples/counter.md) | Signals, memos, holes, and `Prop` defaults. |
| [Async fetch](examples/fetch.md) | Async [`create_memo`][wybthon.create_memo] with a [`Loading`][wybthon.Loading] boundary, refetching, and [`is_pending`][wybthon.is_pending]. |
| [Forms](examples/forms.md) | [`form_state`][wybthon.form_state], bindings, validation, and accessibility helpers. |
| [Error handling](examples/errors.md) | Recovering from render and async errors with [`Errored`][wybthon.Errored]. |
| [Router](examples/router.md) | [`Router`][wybthon.Router], [`Route`][wybthon.Route], [`Link`][wybthon.Link], params, and lazy routes. |
| [Authoring patterns](examples/authoring-patterns.md) | Composition with `children`, lists with `For`, stores, actions, and cleanup. |

!!! tip "Complete apps"

    For full applications that put these patterns together, see the
    [demo apps guide](guides/demo-app.md): standalone repositories like
    [demo-template](https://github.com/wybthon/demo-template) and
    [data-lab](https://github.com/wybthon/data-lab) that run entirely
    in the browser.

## Next steps

- Read the [Concepts](concepts/mental-model.md) section for the underlying mental model.
- Browse the [API reference](api/wybthon.md) when you need precise function signatures.
