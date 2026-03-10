from wybthon import component, div


@component
def NotFound():
    return div("404 - Not Found", style={"color": "#a00"})
