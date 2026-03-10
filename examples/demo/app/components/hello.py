from wybthon import component, h2


@component
def Hello(name: str = "world"):
    return h2(f"Hello, {name}!", class_name="hello")
