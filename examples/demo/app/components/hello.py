from wybthon import component, p


@component
def Hello(name: str = "world"):
    return p(f"Hello, {name}!", class_name="hello")
