from wybthon import h3, section


def Card(props):
    title = props.get("title", "")
    children = props.get("children", [])
    if not isinstance(children, list):
        children = [children]
    return section(h3(title), children, class_name="card")
