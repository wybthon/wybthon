from wybthon import code, component, div, dynamic, h2, h3, p, pre


@component
def Page(params=None):
    """Docs page driven by a wildcard route segment.

    ``params`` is a reactive accessor — call it to read the current
    route params dict.  Wrapping the derived display string in
    :func:`dynamic` keeps the heading reactive without re-mounting the
    component when the URL changes.
    """

    def current_path() -> str:
        p_dict = params() or {}
        wildcard = p_dict.get("wildcard", "")
        return f"/docs/{wildcard}" if wildcard else "/docs/"

    return div(
        div(
            h2("Documentation"),
            p("This page demonstrates wildcard route matching."),
            class_="page-header",
        ),
        div(
            h3("Current Path"),
            p(
                dynamic(current_path),
                style={
                    "fontFamily": "var(--font-mono)",
                    "fontSize": "1.1rem",
                    "color": "var(--primary)",
                    "fontWeight": "600",
                },
            ),
            p("Try navigating to /docs/guide/intro or /docs/api/signals to see the wildcard parameter change."),
            class_="demo-section",
        ),
        div(
            h3("How It Works"),
            p(
                "The route /docs/* captures everything after /docs/ as a "
                '"wildcard" parameter, allowing flexible sub-path matching.'
            ),
            pre(
                code('Route(path="/docs/*", component=DocsPage)'),
                class_="code-block",
            ),
            class_="demo-section",
        ),
        class_="page",
    )
