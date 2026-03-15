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
    count, set_count = create_signal(0)

    def render():
        return div(
            span("Live Demo", class_name="demo-badge"),
            p(f"{count()}", class_name="demo-count"),
            div(
                button("-", on_click=lambda e: set_count(count() - 1)),
                button("+", on_click=lambda e: set_count(count() + 1)),
                class_name="demo-buttons",
            ),
            p(
                f"Double: {count() * 2}  |  Even: {'yes' if count() % 2 == 0 else 'no'}",
                class_name="demo-derived",
            ),
            class_name="hero-demo",
        )

    return render


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
                    "from wybthon import component, create_signal, div, button, p\n"
                    "\n"
                    "@component\n"
                    "def Counter():\n"
                    "    count, set_count = create_signal(0)\n"
                    "\n"
                    "    def render():\n"
                    "        return div(\n"
                    '            p(f"Count: {count()}"),\n'
                    '            button("+", on_click=lambda e: set_count(count() + 1)),\n'
                    "        )\n"
                    "\n"
                    "    return render"
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
                    "Components",
                    "Function components with the @component decorator.",
                ),
                _feature(
                    "Virtual DOM",
                    "Efficient diffing and patching with key-aware reconciliation.",
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
