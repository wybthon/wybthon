from wybthon import (
    button,
    code,
    component,
    create_signal,
    div,
    dynamic,
    h,
    h2,
    h3,
    p,
    pre,
    section,
    span,
)


def _feature(title, desc):
    return div(h3(title), p(desc), class_="feature-card")


@component
def _HeroDemo():
    """Hero demo using the new fully-reactive props model.

    The component body runs **once**.  Each ``span`` / ``p`` text receives
    a getter that becomes a reactive hole — only the relevant text node
    updates when the signal changes.  No component re-render.
    """
    count, set_count = create_signal(0)

    return div(
        span("Live Demo", class_="demo-badge"),
        p(count, class_="demo-count"),
        div(
            button("-", on_click=lambda e: set_count(count() - 1)),
            button("+", on_click=lambda e: set_count(count() + 1)),
            class_="demo-buttons",
        ),
        p(
            "Double: ",
            span(dynamic(lambda: str(count() * 2))),
            "  |  Even: ",
            span(dynamic(lambda: "yes" if count() % 2 == 0 else "no")),
            class_="demo-derived",
        ),
        class_="hero-demo",
    )


@component
def Page():
    return div(
        section(
            h2("Build web apps in pure Python", class_="hero-title"),
            p(
                "Wybthon brings SolidJS-style signals and fine-grained reactivity "
                "to Python. Write modern, interactive frontends entirely in Python, "
                "no JavaScript required.",
                class_="hero-subtitle",
            ),
            h(_HeroDemo, {}),
            class_="hero",
        ),
        section(
            h2("Write components, not configuration", class_="section-title"),
            pre(
                code(
                    "from wybthon import component, create_signal, div, button, p, span\n"
                    "\n"
                    "@component\n"
                    "def Counter(initial=0):\n"
                    "    # Props are reactive accessors.  Use untrack() to seed a signal\n"
                    "    # without subscribing to future updates.\n"
                    "    from wybthon import untrack\n"
                    "    count, set_count = create_signal(untrack(initial))\n"
                    "    # Body runs ONCE.  ``count`` is a zero-arg getter and the\n"
                    "    # surrounding span turns it into a reactive hole: only that\n"
                    "    # text node updates when the signal changes.\n"
                    "    return div(\n"
                    '        p("Count: ", span(count)),\n'
                    '        button("+", on_click=lambda e: set_count(count() + 1)),\n'
                    "    )"
                ),
                class_="code-block",
            ),
            class_="code-section",
        ),
        section(
            h2("Everything you need", class_="section-title"),
            div(
                _feature(
                    "Reactive Props",
                    "Every prop is a getter.  Pass it into the tree for an "
                    "auto-hole, call it for a static value, or wrap in "
                    "untrack() to seed local state.",
                ),
                _feature(
                    "Signals",
                    "Fine-grained reactivity with create_signal, create_effect, and create_memo.",
                ),
                _feature(
                    "Reactive Holes",
                    "Components run once. Embed signal getters anywhere in your "
                    "VNode tree and only the relevant node updates.",
                ),
                _feature(
                    "Reactive Context",
                    "Provider values are signal-backed: changing the value "
                    "ripples to consumers without re-mounting the subtree.",
                ),
                _feature(
                    "Components",
                    "Function components with the @component decorator.",
                ),
                _feature(
                    "Virtual DOM",
                    "Batched, key-aware diffing — efficient for Pyodide's bridge.",
                ),
                _feature(
                    "Routing",
                    "Client-side routing with nested routes, lazy loading, and wildcards.",
                ),
                _feature(
                    "Forms",
                    "Built-in form state, validation rules, and two-way bindings.",
                ),
                _feature(
                    "Async Resources",
                    "Fetch data with create_resource and Suspense for loading states.",
                ),
                _feature(
                    "Context",
                    "Share data across the tree without prop drilling.",
                ),
                _feature(
                    "Error Boundaries",
                    "Graceful error handling with fallback UI and recovery.",
                ),
                class_="feature-grid",
            ),
            class_="features",
        ),
        class_="page home",
    )
