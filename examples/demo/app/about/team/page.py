from wybthon import button, code, component, div, h2, h3, navigate, p, pre


@component
def Page():
    return div(
        div(
            h2("Team"),
            p(
                "This page demonstrates nested routing and lazy loading. "
                "It was loaded on-demand when you navigated here."
            ),
            class_name="page-header",
        ),
        div(
            h3("How It Works"),
            p(
                "This component is defined at /about/team as a child route "
                "of /about. It was lazy-loaded using the lazy() wrapper, "
                "meaning the module is only fetched when you navigate here."
            ),
            class_name="demo-section",
        ),
        div(
            h3("Route Configuration"),
            pre(
                code(
                    "Route(\n"
                    '    path="/about",\n'
                    "    component=lazy(_AboutLazy),\n"
                    "    children=[\n"
                    '        Route(path="team", component=lazy(_TeamLazy)),\n'
                    "    ],\n"
                    ")"
                ),
                class_name="code-block",
            ),
            class_name="demo-section",
        ),
        button("Back to About", on_click=lambda e: navigate("/about")),
        class_name="page",
    )
