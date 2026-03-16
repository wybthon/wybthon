from wybthon import component, p


@component
def Hello(name="world"):
    return p(f"Hello, {name()}!", class_name="hello")
