from wybthon import Link, h


def Nav(_props):
    return h(
        "nav",
        {"class": "nav"},
        h(Link, {"to": "/", "class": "nav-link", "class_active": "active"}, "Home"),
        " | ",
        h(Link, {"to": "/about", "class": "nav-link", "class_active": "active"}, "About"),
        " (",
        h(Link, {"to": "/about/team", "class": "nav-link", "class_active": "active"}, "Team"),
        ")",
        " | ",
        h(Link, {"to": "/fetch", "class": "nav-link", "class_active": "active"}, "Fetch"),
        " | ",
        h(Link, {"to": "/forms", "class": "nav-link", "class_active": "active"}, "Forms"),
        " | ",
        h(Link, {"to": "/errors", "class": "nav-link", "class_active": "active"}, "Errors"),
        " | ",
        h(Link, {"to": "/docs", "class": "nav-link", "class_active": "active"}, "Docs"),
        " (",
        h(Link, {"to": "/docs/guide/intro", "class": "nav-link", "class_active": "active"}, "guide/intro"),
        ")",
        " | ",
        # Example of replace navigation (won't add history entry when clicked)
        h(Link, {"to": "/about", "replace": True, "class": "nav-link", "class_active": "active"}, "About (replace)"),
    )
