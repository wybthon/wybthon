from wybthon import h2


def Hello(props):
    name = props.get("name", "world")
    return h2(f"Hello, {name}!", class_name="hello")
