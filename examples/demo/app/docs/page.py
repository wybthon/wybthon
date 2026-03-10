from wybthon import component, div, h3, p


@component
def Page(params=None):
    params = params or {}
    wildcard = params.get("wildcard", "")
    return div(
        h3("Docs"),
        p(f"Path: {wildcard or '(root)'}"),
    )
