from wybthon import h


def Page(props):
    params = props.get("params", {})
    wildcard = params.get("wildcard", "")
    return h(
        "div",
        {},
        h("h3", {}, "Docs"),
        h("p", {}, f"Path: {wildcard or '(root)'}"),
    )
