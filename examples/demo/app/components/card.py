from wybthon import component, h3, section


@component
def Card(title="", children=None):
    _ch = children()
    kids = _ch if isinstance(_ch, list) else ([_ch] if _ch else [])
    return section(h3(title()), *kids, class_name="card")
