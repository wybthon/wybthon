from app.components.theme_label import ThemeLabel
from wybthon import Link, component, div, h, h2, h3, p


@component
def Page():
    return div(
        div(
            h2("About Wybthon"),
            p(
                "Wybthon is a Python-first, client-side SPA framework for building "
                "interactive web applications in the browser. Powered by Pyodide, it "
                "lets you write modern frontends entirely in Python."
            ),
            class_="page-header",
        ),
        div(
            h3("How It Works"),
            p(
                "Wybthon follows the SolidJS model: signals hold reactive state, "
                "effects re-run when signals change, and memos cache derived values. "
                "Components run **once** and bind to props via reactive accessors, "
                "while the virtual DOM applies fine-grained updates efficiently."
            ),
            class_="demo-section",
        ),
        div(
            h3("Key Concepts"),
            div(
                div(
                    h3("Signals"),
                    p(
                        "Reactive state primitives. Read with a getter, write with "
                        "a setter. Dependencies are tracked automatically."
                    ),
                    class_="concept-card",
                ),
                div(
                    h3("Effects"),
                    p(
                        "Side effects that re-run when tracked signals change. "
                        "Cleanup runs automatically before each re-execution."
                    ),
                    class_="concept-card",
                ),
                div(
                    h3("Reactive Props"),
                    p(
                        "Component parameters are zero-arg getters. Pass them into "
                        "the tree for an auto-hole, or call them for a static value."
                    ),
                    class_="concept-card",
                ),
                div(
                    h3("Context"),
                    p(
                        "Share values across the component tree without passing props "
                        "through every level. Provider values are signal-backed and "
                        "update reactively."
                    ),
                    class_="concept-card",
                ),
                class_="concept-grid",
            ),
            class_="demo-section",
        ),
        div(
            h3("Context in Action"),
            p("The theme value below is read from context using use_context:"),
            h(ThemeLabel, {}),
            class_="demo-section",
        ),
        div(
            h3("Lazy Loading & Nested Routes"),
            p(
                "This page was lazy-loaded. The team sub-page demonstrates "
                "nested routing with lazy-loaded components."
            ),
            h(Link, {"to": "/about/team", "class_": "button"}, "View Team Page"),
            class_="demo-section",
        ),
        class_="page",
    )
