from wybthon import button, component, div, h2, navigate, p


@component
def NotFound():
    return div(
        h2("404"),
        p("The page you're looking for doesn't exist."),
        button("Go Home", on_click=lambda e: navigate("/")),
        class_="not-found",
    )
