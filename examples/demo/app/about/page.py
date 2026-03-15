from app.components.theme_label import ThemeLabel
from wybthon import button, component, div, h, h2, h3, navigate, p


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
            class_name="page-header",
        ),
        div(
            h3("How It Works"),
            p(
                "Wybthon follows the SolidJS model: signals hold reactive state, "
                "effects re-run when signals change, and memos cache derived values. "
                "The virtual DOM handles efficient rendering while fine-grained "
                "reactivity ensures minimal re-renders."
            ),
            class_name="demo-section",
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
                    class_name="concept-card",
                ),
                div(
                    h3("Effects"),
                    p(
                        "Side effects that re-run when tracked signals change. "
                        "Cleanup runs automatically before each re-execution."
                    ),
                    class_name="concept-card",
                ),
                div(
                    h3("Components"),
                    p("Stateful components return a render function. Stateless " "components return VNodes directly."),
                    class_name="concept-card",
                ),
                div(
                    h3("Context"),
                    p("Share values across the component tree without passing " "props through every level."),
                    class_name="concept-card",
                ),
                class_name="concept-grid",
            ),
            class_name="demo-section",
        ),
        div(
            h3("Context in Action"),
            p("The theme value below is read from context using use_context:"),
            h(ThemeLabel, {}),
            class_name="demo-section",
        ),
        div(
            h3("Lazy Loading & Nested Routes"),
            p(
                "This page was lazy-loaded. The team sub-page demonstrates "
                "nested routing with lazy-loaded components."
            ),
            button("View Team Page", on_click=lambda e: navigate("/about/team")),
            class_name="demo-section",
        ),
        class_name="page",
    )
