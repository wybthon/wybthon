from wybthon import component, h3, section


@component
def Card(title: str = "", children=None):
    kids = children if isinstance(children, list) else ([children] if children else [])
    return section(h3(title), *kids, class_name="card")
