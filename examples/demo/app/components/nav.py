from wybthon import Link, h


def Nav(_props):
    return h(
        "nav",
        {},
        h(Link, {"to": "/"}, "Home"),
        " | ",
        h(Link, {"to": "/about"}, "About"),
        " (",
        h(Link, {"to": "/about/team"}, "Team"),
        ")",
        " | ",
        h(Link, {"to": "/fetch"}, "Fetch"),
        " | ",
        h(Link, {"to": "/forms"}, "Forms"),
        " | ",
        h(Link, {"to": "/errors"}, "Errors"),
        " | ",
        h(Link, {"to": "/docs"}, "Docs"),
        " (",
        h(Link, {"to": "/docs/guide/intro"}, "guide/intro"),
        ")",
    )
