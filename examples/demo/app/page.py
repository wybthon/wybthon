from wybthon import (
    button,
    code,
    component,
    create_signal,
    div,
    h,
    h2,
    h3,
    p,
    pre,
    section,
    span,
)


def _feature(title, desc):
    return div(h3(title), p(desc), class_name="feature-card")


@component
def _HeroDemo():
    """Hero demo using the new fine-grained model.

    The component body runs **once**; each ``span`` / ``p`` text receives
    a getter that becomes a reactive hole.  Only the relevant text node
    updates when the signal changes — no component re-render.
    """
    count, set_count = create_signal(0)

    return div(
        span("Live Demo", class_name="demo-badge"),
        p(count, class_name="demo-count"),
        div(
            button("-", on_click=lambda e: set_count(count() - 1)),
            button("+", on_click=lambda e: set_count(count() + 1)),
            class_name="demo-buttons",
        ),
        p(
            "Double: ",
            span(lambda: str(count() * 2)),
            "  |  Even: ",
            span(lambda: "yes" if count() % 2 == 0 else "no"),
            class_name="demo-derived",
        ),
        class_name="hero-demo",
    )


@component
def Page():
    return div(
        section(
            h2("Build web apps in pure Python", class_name="hero-title"),
            p(
                "Wybthon brings SolidJS-style signals and fine-grained reactivity "
                "to Python. Write modern, interactive frontends entirely in Python, "
                "no JavaScript required.",
                class_name="hero-subtitle",
            ),
            h(_HeroDemo, {}),
            class_name="hero",
        ),
        section(
            h2("Write components, not configuration", class_name="section-title"),
            pre(
                code(
                    "from wybthon import component, create_signal, div, button, p, span\n"
                    "\n"
                    "@component\n"
                    "def Counter(initial=0):\n"
                    "    count, set_count = create_signal(initial)\n"
                    "    # Body runs ONCE.  ``count`` is a zero-arg getter and\n"
                    "    # the surrounding span turns it into a reactive hole:\n"
                    "    # only that text node updates when the signal changes.\n"
                    "    return div(\n"
                    '        p("Count: ", span(count)),\n'
                    '        button("+", on_click=lambda e: set_count(count() + 1)),\n'
                    "    )"
                ),
                class_name="code-block",
            ),
            class_name="code-section",
        ),
        section(
            h2("Everything you need", class_name="section-title"),
            div(
                _feature(
                    "Signals",
                    "Fine-grained reactivity with create_signal, create_effect, " "and create_memo.",
                ),
                _feature(
                    "Reactive Holes",
                    "Components run once. Embed signal getters anywhere in your "
                    "VNode tree and only the relevant node updates.",
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
                    "Client-side routing with nested routes, lazy loading, " "and wildcards.",
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
                class_name="feature-grid",
            ),
            class_name="features",
        ),
        class_name="page home",
    )
