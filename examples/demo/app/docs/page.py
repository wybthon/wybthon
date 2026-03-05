from wybthon import div, h3, p


def Page(props):
    params = props.get("params", {})
    wildcard = params.get("wildcard", "")
    return div(
        h3("Docs"),
        p(f"Path: {wildcard or '(root)'}"),
    )
