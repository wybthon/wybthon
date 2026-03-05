from wybthon import Link, h, nav, preload_component


def Nav(props):
    base_path = props.get("base_path")

    def on_hover_team(_evt):
        try:
            preload_component("app.about.team.page", "Page")
        except Exception:
            pass

    link_props = {"base_path": base_path, "class": "nav-link", "class_active": "active"}

    return nav(
        h(Link, {**link_props, "to": "/"}, "Home"),
        " | ",
        h(Link, {**link_props, "to": "/about"}, "About"),
        " (",
        h(Link, {**link_props, "to": "/about/team", "on_mouseover": on_hover_team}, "Team"),
        ")",
        " | ",
        h(Link, {**link_props, "to": "/fetch"}, "Fetch"),
        " | ",
        h(Link, {**link_props, "to": "/forms"}, "Forms"),
        " | ",
        h(Link, {**link_props, "to": "/errors"}, "Errors"),
        " | ",
        h(Link, {**link_props, "to": "/patterns"}, "Patterns"),
        " | ",
        h(Link, {**link_props, "to": "/docs"}, "Docs"),
        " (",
        h(Link, {**link_props, "to": "/docs/guide/intro"}, "guide/intro"),
        ")",
        " | ",
        h(Link, {**link_props, "to": "/about", "replace": True}, "About (replace)"),
        class_name="nav",
    )
