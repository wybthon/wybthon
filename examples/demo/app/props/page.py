"""Demos for the *fully-reactive props model*.

Wybthon's component model runs each component **once** and exposes
every prop as a zero-arg callable accessor.  The same accessor is the
read API and the auto-hole API:

* ``name`` (the accessor) → reactive when embedded in a VNode tree
* ``name()`` → current value (tracked when called inside an effect)
* ``untrack(name)`` → snapshot value without subscribing

These demos walk through each shape.
"""

from wybthon import (
    Provider,
    button,
    code,
    component,
    create_context,
    create_signal,
    div,
    dynamic,
    h,
    h2,
    h3,
    p,
    pre,
    section,
    span,
    untrack,
    use_context,
)

# --------------------------------------------------------------------------- #
# Demo 1 -- accessor as auto-hole vs explicit call
# --------------------------------------------------------------------------- #


@component
def _Greeter(name="world"):
    """Render greeting with two prop access patterns side-by-side."""
    return div(
        p("Auto-hole: Hello, ", name, "!"),
        p("Static snapshot: Hello, ", untrack(name), "!"),
        p("Inside dynamic: ", dynamic(lambda: f"Hello, {name()}!")),
        class_="demo-section nested",
    )


@component
def AccessorShapes():
    name, set_name = create_signal("Ada")

    return div(
        h3("Accessor shapes"),
        p(
            "The same prop accessor can be passed as a child (reactive auto-hole), "
            "called once with ``untrack`` (static snapshot), or called inside "
            "``dynamic(...)`` (custom derivation that re-evaluates as the prop changes)."
        ),
        div(
            button("Ada", on_click=lambda e: set_name("Ada")),
            button("Grace", on_click=lambda e: set_name("Grace")),
            button("Linus", on_click=lambda e: set_name("Linus")),
            style={"display": "flex", "gap": "8px"},
        ),
        h(_Greeter, {"name": name}),
        class_="demo-section",
    )


# --------------------------------------------------------------------------- #
# Demo 2 -- prop transparently accepts static or getter
# --------------------------------------------------------------------------- #


@component
def _Badge(label="?", count=0):
    return span(
        label,
        ": ",
        dynamic(lambda: str(count())),
        class_="pill",
        style={"fontVariantNumeric": "tabular-nums"},
    )


@component
def StaticOrGetter():
    """A child component never has to care whether the parent passes a
    static value or a signal accessor -- both are unwrapped uniformly.
    """
    n, set_n = create_signal(0)

    return div(
        h3("Static or getter (transparent)"),
        p(
            "Both badges below use the same ``count`` prop.  The first is "
            "passed a constant, the second is passed a signal accessor.  "
            "Click the button -- only the second updates."
        ),
        div(
            h(_Badge, {"label": "Static", "count": 7}),
            h(_Badge, {"label": "Live", "count": n}),
            style={"display": "flex", "gap": "8px"},
        ),
        button("+1", on_click=lambda e: set_n(n() + 1)),
        class_="demo-section",
    )


# --------------------------------------------------------------------------- #
# Demo 3 -- reactive context updates without re-mount
# --------------------------------------------------------------------------- #

Locale = create_context("en")


@component
def _LocaleLabel():
    return p("Current locale: ", dynamic(lambda: use_context(Locale)))


@component
def ReactiveContext():
    locale, set_locale = create_signal("en")

    cycle = {"en": "fr", "fr": "ja", "ja": "es", "es": "en"}

    return div(
        h3("Reactive context"),
        p(
            "``Provider``'s ``value`` is signal-backed.  The label below "
            "is a child component that reads ``use_context`` -- it updates "
            "without being re-mounted."
        ),
        button(
            dynamic(lambda: f"Cycle locale ({locale()})"),
            on_click=lambda e: set_locale(cycle.get(locale(), "en")),
        ),
        h(Provider, {"context": Locale, "value": locale}, h(_LocaleLabel, {})),
        class_="demo-section",
    )


# --------------------------------------------------------------------------- #
# Demo 4 -- proxy mode for advanced introspection
# --------------------------------------------------------------------------- #


@component
def _DumpProps(props):
    """Single-positional-parameter component receives the ``ReactiveProps`` proxy directly."""
    return div(
        p("Keys (live): ", dynamic(lambda: ", ".join(sorted(list(props))))),
        p("Values (live): ", dynamic(lambda: ", ".join(f"{k}={props.value(k)!r}" for k in sorted(list(props))))),
        class_="demo-section nested",
    )


@component
def ProxyMode():
    a, set_a = create_signal(1)
    b, set_b = create_signal("x")

    return div(
        h3("Proxy mode"),
        p(
            "When a component declares a single positional parameter with no "
            "default, the decorator passes the ``ReactiveProps`` proxy directly. "
            "This is useful for generic wrappers or when iterating prop keys."
        ),
        div(
            button("a++", on_click=lambda e: set_a(a() + 1)),
            button("b cycle", on_click=lambda e: set_b("y" if b() == "x" else "x")),
            style={"display": "flex", "gap": "8px"},
        ),
        h(_DumpProps, {"a": a, "b": b}),
        class_="demo-section",
    )


# --------------------------------------------------------------------------- #
# Page
# --------------------------------------------------------------------------- #


_INTRO = """\
* Pass an accessor into the tree for a reactive auto-hole: ``p(name)``
* Call it for the current value: ``name()``
* Use ``untrack`` to seed local state without subscribing
* ``Provider`` accepts a getter for ``value`` -- consumers update reactively
* Single-positional components receive the ``ReactiveProps`` proxy directly"""


@component
def Page():
    return div(
        div(
            h2("Reactive Props"),
            p(
                "Components run once.  Props are zero-arg getters with one consistent shape.",
                class_="page-subtitle",
            ),
            class_="page-header",
        ),
        section(
            pre(code(_INTRO), class_="code-block"),
            class_="code-section",
        ),
        h(AccessorShapes, {}),
        h(StaticOrGetter, {}),
        h(ReactiveContext, {}),
        h(ProxyMode, {}),
        class_="page",
    )
