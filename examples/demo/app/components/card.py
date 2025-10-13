from wybthon import h


def Card(props):
    title = props.get("title", "")
    children = props.get("children", [])
    if not isinstance(children, list):
        children = [children]
    return h("section", {"class": "card"}, h("h3", {}, title), children)
