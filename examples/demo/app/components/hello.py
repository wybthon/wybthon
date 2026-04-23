from wybthon import component, p


@component
def Hello(name="world"):
    """Greeting component.  ``name`` is a reactive accessor; passing it
    directly into the tree creates an automatic reactive hole, so when
    the parent updates the prop only the text node re-renders.
    """
    return p("Hello, ", name, "!", class_="hello")
