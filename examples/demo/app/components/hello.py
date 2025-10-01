from wybthon import h


def Hello(props):
    name = props.get("name", "world")
    return h("h2", {"class": "hello"}, f"Hello, {name}!")
