from wybthon import code, component, div, h2, h3, p, pre


@component
def Page(params=None):
    params = params() or {}
    wildcard = params.get("wildcard", "")
    return div(
        div(
            h2("Documentation"),
            p("This page demonstrates wildcard route matching."),
            class_name="page-header",
        ),
        div(
            h3("Current Path"),
            p(
                f"/docs/{wildcard}" if wildcard else "/docs/",
                style={
                    "fontFamily": "var(--font-mono)",
                    "fontSize": "1.1rem",
                    "color": "var(--primary)",
                    "fontWeight": "600",
                },
            ),
            p("Try navigating to /docs/guide/intro or /docs/api/signals " "to see the wildcard parameter change."),
            class_name="demo-section",
        ),
        div(
            h3("How It Works"),
            p(
                "The route /docs/* captures everything after /docs/ as a "
                '"wildcard" parameter, allowing flexible sub-path matching.'
            ),
            pre(
                code('Route(path="/docs/*", component=DocsPage)'),
                class_name="code-block",
            ),
            class_name="demo-section",
        ),
        class_name="page",
    )
