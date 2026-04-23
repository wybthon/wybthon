from wybthon import component, dynamic, h3, section, untrack


@component
def Card(title="", children=None):
    """Simple titled card.

    ``title`` updates reactively (passed straight into the tree).
    Children are read once at setup using :func:`untrack` -- the new
    model passes them as a getter, but the children list itself rarely
    changes once the card is mounted.
    """
    kids = untrack(children) if callable(children) else children
    if kids is None:
        kids = []
    if not isinstance(kids, list):
        kids = [kids]
    return section(h3(dynamic(lambda: title())), *kids, class_="card")
