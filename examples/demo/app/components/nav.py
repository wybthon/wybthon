from wybthon import Link, h


def Nav(props):
    base_path = props.get("base_path")
    return h(
        "nav",
        {"class": "nav"},
        h(Link, {"to": "/", "base_path": base_path, "class": "nav-link", "class_active": "active"}, "Home"),
        " | ",
        h(Link, {"to": "/about", "base_path": base_path, "class": "nav-link", "class_active": "active"}, "About"),
        " (",
        h(Link, {"to": "/about/team", "base_path": base_path, "class": "nav-link", "class_active": "active"}, "Team"),
        ")",
        " | ",
        h(Link, {"to": "/fetch", "base_path": base_path, "class": "nav-link", "class_active": "active"}, "Fetch"),
        " | ",
        h(Link, {"to": "/forms", "base_path": base_path, "class": "nav-link", "class_active": "active"}, "Forms"),
        " | ",
        h(Link, {"to": "/errors", "base_path": base_path, "class": "nav-link", "class_active": "active"}, "Errors"),
        " | ",
        h(Link, {"to": "/docs", "base_path": base_path, "class": "nav-link", "class_active": "active"}, "Docs"),
        " (",
        h(
            Link,
            {"to": "/docs/guide/intro", "base_path": base_path, "class": "nav-link", "class_active": "active"},
            "guide/intro",
        ),
        ")",
        " | ",
        # Example of replace navigation (won't add history entry when clicked)
        h(
            Link,
            {"to": "/about", "base_path": base_path, "replace": True, "class": "nav-link", "class_active": "active"},
            "About (replace)",
        ),
    )
