# Troubleshooting

If something isn't working as expected, scan this page for the symptom you're seeing. Each entry includes the most likely cause and a fix; expand for more detail.

## Setup

??? bug "`SyntaxError` or `ImportError` on import under an older Python"

    **Symptoms:** importing `wybthon` in CPython fails with a syntax error at a `t"..."` string, an `ImportError` for `string.templatelib` or `annotationlib`, or `pip` refuses to install.

    **Likely cause:** Wybthon requires Python 3.14 (template strings and deferred annotations). In the browser that means Pyodide 314 or newer.

    **Fix:** upgrade the interpreter (`uv python install 3.14` works well) and re-create your virtual environment. Set `pyodide-version` in `wybthon.toml` to a 314 release.

??? bug "`ImportError: cannot import name 'Router' from 'wybthon'`"

    **Symptoms:** importing `Router`, `Route`, `Link`, `navigate`, `form_state`, `bind_text`, `VirtualFor`, or `map_cooperative` from `wybthon` fails.

    **Likely cause:** the top-level package exports the core only. The router, forms, virtual lists, and scheduling helpers live in their own modules.

    **Fix:** import them from `wybthon.router`, `wybthon.forms`, `wybthon.virtual`, and `wybthon.scheduling`, for example `from wybthon.router import Link, Router`.

??? bug "`ImportError: cannot import name 'div' from 'wybthon'`"

    **Symptoms:** importing `div`, `p`, `button`, `input_`, `element`, or another element helper fails, or `import wybthon.elements` (or `wybthon.svg`, or the older `from wybthon.html import div`) raises `ModuleNotFoundError`.

    **Likely cause:** [RFC 0004](../rfcs/0004-engine-v4.md) removed the element helpers. A helper evaluates its arguments before Wybthon sees them, so it can't benefit from the compiler. `wybthon.html` is the [`html`][wybthon.html] template function, not a module.

    **Fix:** write markup as templates, `html(t'<div class="card">{props.title}</div>')`; `<svg>` works in a template too. Where code builds the markup (a generated form, a recursive tree, a computed tag), use [`h(tag, props, *children)`][wybthon.h]. See [Templates](../concepts/templates.md).

??? bug "Pyodide fails to load"

    **Symptoms:** the page renders nothing; the browser console shows a network error or an `Importing pyodide failed` message.

    **Likely causes:**

    - The CDN URL referenced from your `index.html` is unreachable (offline development, corporate firewall, ad blocker).
    - You bumped the Pyodide version but the matching `pyodide.js` and `pyodide.asm.wasm` files weren't refreshed together.

    **Fix:**

    1. Check the network tab and confirm the Pyodide assets return `200`.
    2. Try loading from a local copy by self-hosting the Pyodide release that matches your `pyodide.js` URL.
    3. If using a corporate CDN, allowlist the Pyodide host(s) and the `*.wasm` content type.

??? bug "`mkdocs build --strict` fails after updating docs"

    **Symptoms:** the docs site builds locally with `mkdocs serve` but `mkdocs build --strict` fails.

    **Likely cause:** an unresolved cross-reference (for example a typo in a `[label][wybthon.symbol]` link, or a link to a name that was removed in the API overhaul) or an unused `nav` entry.

    **Fix:** read the warning text. `mkdocstrings` reports the exact symbol it couldn't find, so update the page or the symbol's docstring accordingly. If the broken link is intentional (for example, while a feature is in flight), turn the link into plain text or remove it.

## Templates

??? bug "`TemplateError: {count() * 2} was evaluated once instead of becoming reactive, because this template wasn't compiled`"

    **Symptoms:** in dev mode, calling [`html`][wybthon.html] raises [`TemplateError`][wybthon.TemplateError] naming an interpolation, followed by the template:

    ```text
    {count() * 2} was evaluated once instead of becoming reactive, because this template wasn't compiled.
    Templates compile automatically in modules imported after wybthon, in wyb build and wyb dev, and under
    pytest; run a script with `wyb run script.py`, or wrap the expression in a lambda.
      in template: t'<p>{...}</p>'
    ```

    **Likely cause:** Wybthon's compiler turns each dynamic interpolation (one with a call, an attribute access, or a subscript) into a getter before the module runs. This template reached `html()` without being compiled, so Python had already evaluated `count() * 2` once, and the markup would silently stop updating. The import hook that `import wybthon` installs only compiles modules imported after it, so templates go uncompiled when they're written in a script run directly with `python script.py`, typed at a REPL, built with `exec`, or in a module that was already loading when `wybthon` was first imported (for example `python -c "import app"`, where `app.py` is the first module to import `wybthon`).

    **Fix:** run scripts with `wyb run script.py` instead of `python script.py`; it compiles the script and everything it imports. Otherwise, import `wybthon` before the modules that contain templates. `wyb build` and `wyb dev` compile the whole application. Tests are compiled by the pytest plugin, and code that builds a module's source at run time can compile it with [`compile_source`][wybthon.compiler.compile_source] before `exec`. At a REPL, wrap the expression in a lambda, `{(lambda: count() * 2)}`, or pass the accessor itself, `{count}`. See [The compiler](../concepts/compiler.md).

??? bug "`SyntaxError: t-string: lambda expressions are not allowed without parentheses`"

    **Symptoms:** the module containing a template fails to import, pointing at a `lambda` inside `{...}`, such as `html(t"<button onclick={lambda: set_open(False)}>Close</button>")`.

    **Likely cause:** Python's grammar doesn't allow a bare `lambda` in a t-string (or f-string) interpolation, because its `:` would start a format spec. The error comes from Python itself, before Wybthon runs.

    **Fix:** give the handler a name, or wrap the lambda in parentheses:

    ```python
    from wybthon import create_signal, html

    is_open, set_open = create_signal(True)


    def close():
        set_open(False)


    html(t"<button onclick={close}>Close</button>")  # a named handler
    html(t"<button onclick={(lambda: set_open(False))}>Close</button>")  # parentheses
    ```

    Values don't need a lambda at all: the compiler keeps `{count() * 2}` and `class={"on" if active() else ""}` reactive as written. A lambda passed as an argument inside the interpolation is fine, because it's already inside parentheses: `{For(todos(), lambda todo, i: row(todo))}`.

??? bug "`TemplateError: <tr> can't be a child of <table> (add a <tbody>)`"

    **Symptoms:** importing a module fails with a `SyntaxError` at a template's file and line, or (for a template that wasn't compiled) calling [`html`][wybthon.html] raises [`TemplateError`][wybthon.TemplateError] the first time it runs. The message names the problem and quotes the template:

    ```text
    <tr> can't be a child of <table> (add a <tbody>)
      in template: t'<table><tr><td>{...}</td></tr></table>' (views.py, line 3)
    ```

    **Likely cause:** the markup is malformed, or the browser's HTML parser would silently rearrange it. The compiler checks each template when it compiles the module, so the error names the file and line. Wybthon clones exactly the nodes the template describes, so it rejects markup that wouldn't parse back to the same tree. Other messages you may see:

    - `<div> can't be inside <p>; the HTML parser would close the <p>`: block content inside a paragraph. Use a `<div>` for the outer element, or an inline element inside.
    - `<a> can't be nested inside another <a>`: links, buttons, and forms can't contain themselves, even through other elements.
    - `Closing tag </div> doesn't match <span>`: a missing or misordered closing tag.
    - Text directly inside `<tbody>` or another table section, a `<li>` directly inside a `<li>`, and an interpolation inside `<script>`, `<style>`, or `<textarea>` are rejected too.

    **Fix:** write the markup the parser expects, for example `<table><tbody><tr>...</tr></tbody></table>`. Give a `<textarea>` its value with `value={...}`. See [Templates](../concepts/templates.md#markup-the-parser-would-rewrite-is-an-error).

??? bug "A template attribute such as `class_` shows up literally in the DOM"

    **Symptoms:** the rendered element has an attribute named `class_` or `html_for`, and no class or label association.

    **Likely cause:** templates use HTML attribute names. The Python spellings (`class_`, `html_for`, `aria_label`) belong to [`h()`][wybthon.h] props.

    **Fix:** write `class`, `for`, and `aria-label` in templates. Event attributes accept `onclick`, `onClick`, and `on:click`. A spread (`<input {attrs}>`) is the exception: its mapping uses `h()`'s Python names, such as `on_input` and `aria_label`.

??? bug "A component tag receives a dict, or its props aren't checked by my type checker"

    **Symptoms:** a plain function used as `<{fn} ...>` gets one dictionary argument instead of keyword arguments, or pyright doesn't flag a misspelled prop in `<{Card} titel="Hi" />`.

    **Likely cause:** the tag form calls a [`@component`][wybthon.component] with keyword props. Any other callable is called the way its signature takes children: with a `children` keyword (`Show`, `Loading`), with positional children (`Link`, context providers), or, for a function whose only parameter is the props, with the props dictionary. Type checkers can't see inside the template string, so tag props are only checked at run time, in dev mode.

    **Fix:** decorate the function with `@component` and give it a `Props` class, or call it inside an interpolation (`{Link("Home", href="/")}`), which is type-checked like any other call. The compiler still passes getters for the call's dynamic arguments, so `{Card(title=user().name)}` stays reactive.

## Components and props

??? bug "`TypeError: Card() got unexpected prop(s): ...` or `is missing required prop(s): ...`"

    **Symptoms:** calling a component raises `TypeError` at the call site in dev mode.

    **Likely cause:** the call passes a keyword its props class doesn't declare (often a typo), or leaves out a field with no default. There's no `**rest`: a component accepts only what it declares, plus `key` and `children`.

    **Fix:** fix the name, add the field to the props class, or give it a default (`body: str = ""`). Pyright and mypy report the same mistakes before you run the code; see the [typing guide](../guides/typing.md).

??? bug "`TypeError: Component X must take no parameters or one parameter annotated with a Props subclass`"

    **Symptoms:** a component raises when it's first called.

    **Likely cause:** the function uses parameter-style props (`def Card(title: str)`), several parameters, `**rest`, or an annotation that isn't a `Props` subclass.

    **Fix:** move the inputs onto a props class and take it as the only parameter:

    ```python
    from wybthon import Props, component, html


    class CardProps(Props):
        title: str = ""


    @component
    def Card(props: CardProps):
        return html(t"<h2>{props.title}</h2>")
    ```

    A component with no inputs takes no parameters. If the annotation is defined later in the module, make sure the name resolves by the time the component is first called.

??? bug "`TypeError: prop() takes 0 positional arguments`, or `prop() takes exactly one of default= or default_factory=`"

    **Likely cause:** `prop(0)` passes the default positionally, or `prop()` is called with neither (or both) of its keywords.

    **Fix:** most fields don't need `prop()`: write an ordinary default (`step: int = 1`). Use `prop(default_factory=list)` for a mutable default, which runs once per component instance, and pass `default=` or `default_factory=` by keyword.

??? bug "A callback prop runs when it's read, or returns `None`"

    **Symptoms:** reading `props.on_save` calls the function (and returns its result), or `props.render_row` returns a value instead of the function the parent passed.

    **Likely cause:** reading a field unwraps an accessor or zero-argument function, so a prop the parent passes as `{user().name}` or as a signal reads as the value. A field whose annotation is callable (`Callable[...]` or `Accessor[...]`, alone or in a union with `None`) is exempt, and returns what the parent passed. A callback field annotated `Any` or `object` isn't.

    **Fix:** annotate callbacks as callables: `on_save: Callable[[], None] | None = None`. See the [typing guide](../guides/typing.md).

??? bug "The error fallback shows an accessor instead of the message"

    **Symptoms:** an `Errored` fallback renders something like `<wybthon.error_boundary._ErrorAccessor object at 0x...>` where the error message should be.

    **Likely cause:** the fallback's `err` argument is an accessor, as in Solid 2.0, and `str(err)` formats the accessor itself.

    **Fix:** call it inside the template, `html(t"<p>Error: {err()}</p>")`, which the compiler keeps reactive, or call it in code that needs the exception itself.

## Reactive bugs

??? bug "`WriteInScopeError: Cannot write a signal inside a tracking scope`"

    **Symptoms:** a `WriteInScopeError` is raised from a `set_*` call made inside a memo body, a `create_tracked_effect`, a reactive hole (an expression in a template), or a store setter called from one of those.

    **Likely cause:** writing a signal from a tracking scope is almost always a bug: it either creates a feedback loop or hides a value that should be derived.

    **Fix:** derive the value with [`create_memo`][wybthon.create_memo] (or [`create_projection`][wybthon.create_projection] for stores) instead of writing it, or move the write into the untracked `apply` stage of a split effect, `create_effect(compute, apply)`, an event handler, or an [`action`][wybthon.action]. The check only runs in dev mode, but leaving the write in place means the bug ships silently; fix it rather than calling `set_dev_mode(False)`.

??? bug "A component reads a prop or signal but doesn't update"

    **Symptoms:** the console shows `[wybthon] Warning: Component <X> read reactive value prop '<name>' at the top level of its body.` during the first render, and the value never changes afterwards.

    **Likely cause:** you read `props.title` or `count()` in the component body before returning the tree, for example `label = props.title.upper()`. Components run once, so that read isn't tracked and its value is frozen.

    **Fix:** move the read into the template, where the compiler keeps it reactive (`<span>{props.title.upper()}</span>`), or derive it with `create_memo`. If a one-time read is what you want (seeding local state, for example), make it explicit with [`untrack`][wybthon.untrack], `untrack(lambda: props.initial)`, or `count.peek()` for a signal; both silence the warning. Reading a prop the parent passed as a constant doesn't warn.

??? bug "My signal read shows the old value right after I set it"

    **Symptoms:** `set_count(1); assert count() == 1` fails; `count()` still returns `0`.

    **Likely cause:** writes are **staged**. The setter records the new value, and reads return the committed value until the next flush. In the browser that happens automatically (a microtask, and at the end of every event handler), but synchronous test code observes the state before the flush.

    **Fix:** call [`flush`][wybthon.flush] after your writes in tests and scripts. Inside a handler, use a functional update (`set_count(lambda n: n + 1)`) when the next write depends on the previous one; updaters see the staged value.

??? bug "My effect didn't run when I created it"

    **Symptoms:** `create_tracked_effect(lambda: print(count()))` prints nothing until something changes (or until you call `flush()`).

    **Likely cause:** the first run of [`create_effect`][wybthon.create_effect] is deferred to the effect phase of the next flush, after the DOM commit, so effects created in a component body observe the mounted DOM.

    **Fix:** in tests, call `flush()` after creating the effect. In components, this is the behavior you want; use [`on_settled`][wybthon.on_settled] for one-time post-mount work and [`untrack`][wybthon.untrack] for a synchronous read during setup.

??? bug "`NotReadyError: Async computation has no value yet`"

    **Symptoms:** calling an async memo (one whose body is `async def`) from an event handler, a component body, or plain script code raises `NotReadyError`. Or, in the tree, a hole that reads the memo renders nothing and no loading indicator appears.

    **Likely cause:** the read happened before the memo produced its first value. Inside a hole, memo, or effect the framework handles this: the reader stays pending and the nearest [`Loading`][wybthon.Loading] boundary shows its fallback. Without a `Loading` above it, the hole simply stays empty until the value arrives; outside any tracking scope the exception surfaces to your code.

    **Fix:** wrap the consuming subtree in `Loading(..., fallback=...)`. To read from imperative code, use [`latest`][wybthon.latest] (returns the stale value or `None`), guard with [`is_pending`][wybthon.is_pending], or `await resolve(memo)` in async code.

??? bug "`ContextNotFoundError` from `use_context`"

    **Symptoms:** `use_context(Theme)` raises `ContextNotFoundError: use_context(Context(Theme)) found no provider above the caller and the context has no default.`

    **Likely causes:**

    - The provider isn't an ancestor in the *reactive* tree: `Theme(value, *children)` must wrap the component that reads it.
    - `use_context` was called outside any reactive scope (module level, or after an `await` without restoring the owner).
    - The context was created without a default.

    **Fix:** move the provider above the reader; capture [`get_owner`][wybthon.get_owner] before an `await` and call `use_context` inside [`run_with_owner`][wybthon.run_with_owner]; or pass a `default=` to [`create_context`][wybthon.create_context] when a missing provider is acceptable.

??? bug "`For` rendered once and never updated"

    **Symptoms:** the list renders correctly the first time, then stops responding to updates. The console shows `[wybthon] Warning: For received a plain list for `each=`.`

    **Likely cause:** `For` was called in ordinary Python code with the list's current value, `For(items(), row)`, so it received a plain list. Inside a template the compiler passes a getter instead, which is why `{For(items(), row)}` works there.

    **Fix:** write the call inside the template, `html(t"<ul>{For(items(), row)}</ul>")`, or pass the accessor itself in Python code: `For(items, row)` (the getter from [`create_signal`][wybthon.create_signal], a memo, or a store list). If the row callback needs the item to be live, use `keyed=False` or a key function so it receives an item accessor.

??? bug "An effect fires forever or `reactive update did not stabilize`"

    **Symptoms:** the browser freezes, or a `RuntimeError: Wybthon: reactive update did not stabilize` is raised from `flush()`.

    **Likely cause:** an effect writes a signal it also reads, so every flush dirties it again.

    **Fix:** split the effect into `create_effect(compute, apply)` so the write happens in the untracked `apply` stage against a value that doesn't feed back, or replace the effect with a memo.

## DOM and events

??? bug "Click handler never fires"

    **Symptoms:** no console log, no state change.

    **Likely causes:**

    - The name is misspelled. Templates expect `onclick`, `oninput`, `onchange`, and so on (`onClick` and `on:click` also work); `h()` props and spreads expect `on_click`, `on_input`, and `on_change`.
    - The event type doesn't bubble (`focus`, `blur`, `mouseenter`, `scroll`); delegation only sees bubbling events.
    - The element lives outside every container passed to [`render`][wybthon.render] (for example a [`Portal`][wybthon.Portal] mounted into `body`), so no delegation root receives the event.
    - The handler returns a coroutine without scheduling it; nothing happens but no error is raised.

    **Fix:** confirm the name, switch to a bubbling type (`focusin`, `mouseover`) or attach a native listener through a [`Ref`][wybthon.Ref] in [`on_settled`][wybthon.on_settled], keep portal targets inside a render container, and schedule async handlers with `asyncio.create_task(...)` or wrap them in an [`action`][wybthon.action].

??? bug "`ref.current` is `None` when I read it"

    **Symptoms:** `ref.current` is `None` inside the component body, but works inside a click handler.

    **Likely cause:** you read the ref before the element mounted.

    **Fix:** read the ref inside [`on_settled`][wybthon.on_settled], an effect, or an event handler; all of them run after the first commit.

??? bug "A boolean attribute renders as `disabled=\"false\"`"

    **Symptoms:** the element stays disabled even though you passed `False`.

    **Likely cause:** you passed the string `"false"` rather than the boolean.

    **Fix:** pass a real boolean or an accessor returning one. `True` sets the attribute, and `False` or `None` removes it.

## Dev server and builds

??? bug "`wyb dev` says the directory has no `wybthon.toml`"

    **Likely cause:** the dev server only serves Wybthon projects; the static-directory mode, `--mount`, `--watch`, and `/__manifest` are gone.

    **Fix:** run `wyb dev` from the project directory (or pass `--dir`), or create a project with `wyb init`. See the [dev server guide](../guides/dev-server.md).

??? bug "SSE reloads not firing"

    **Symptoms:** edits to source files don't trigger a browser refresh.

    **Likely causes:**

    - The edited file isn't watched. `wyb dev` watches the application directory, `public/`, `index.html`, and `wybthon.toml`.
    - The rebuild failed. The terminal shows the build error, and the previous output keeps serving.
    - A reverse proxy in front of the dev server buffers responses and breaks the persistent `/__sse` connection.

    **Fix:** check the terminal output, ensure `/__sse` returns `text/event-stream`, and make sure any proxy supports HTTP/1.1 streaming.

??? bug "Deep links return 404 in production"

    **Symptoms:** the home page loads, but reloading `/users/1` on the deployed site returns 404.

    **Likely cause:** the static host has no fallback for routes that weren't prerendered.

    **Fix:** configure the host to serve `200.html` for missing extensionless routes, and serve the app beneath the `base` path it was built for. See the [deployment guide](../guides/deployment.md).

??? bug "Dev warnings disappeared after deploying"

    **Likely cause:** this is intended. `wyb build` turns dev mode off before the application imports, so production builds skip development checks (including prop validation) and warnings.

    **Fix:** reproduce the problem with `wyb dev`, which keeps dev mode on.

## When all else fails

- Reproduce the problem in a unit test with [`wybthon.testing`][wybthon.testing]; it renders components in plain CPython.
- Capture a minimal reproduction and [open an issue](https://github.com/wybthon/wybthon/issues/new).
- Turn dev mode off with [`set_dev_mode(False)`][wybthon.set_dev_mode] only after you've confirmed the warnings aren't pointing at a real bug. Production builds already do.

## Next steps

- Skim the [FAQ](faq.md) for common questions.
- Read [Reactivity](../concepts/reactivity.md) for a refresher on signals, effects, and reactive holes.
- See the [testing guide](../guides/testing.md) for rendering components and firing events in CPython.
