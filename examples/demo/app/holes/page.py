"""Demos for *reactive holes* — fine-grained reactive expressions.

A reactive hole is a zero-arg callable embedded in a ``VNode`` tree
(child or prop value).  The reconciler wraps each hole in its own
effect, so the surrounding component body runs **once** while the
hole updates the DOM in place when its dependencies change.
"""

from wybthon import (
    button,
    code,
    component,
    create_memo,
    create_signal,
    div,
    dynamic,
    h,
    h2,
    h3,
    input_,
    p,
    pre,
    section,
    span,
)

# --------------------------------------------------------------------------- #
# Demo 1 — text hole
# --------------------------------------------------------------------------- #


@component
def TextHole():
    """A signal getter passed as a child becomes a reactive text hole."""
    count, set_count = create_signal(0)

    return div(
        h3("Text hole"),
        p("The component body runs once. Only the highlighted text node updates when the signal changes."),
        p("Value: ", span(count, class_="hole-value")),
        button("+1", on_click=lambda e: set_count(count() + 1)),
        button("Reset", on_click=lambda e: set_count(0)),
        class_="demo-section",
    )


# --------------------------------------------------------------------------- #
# Demo 2 — explicit dynamic() helper with a derived expression
# --------------------------------------------------------------------------- #


@component
def DynamicHelper():
    """Use ``dynamic(getter)`` to wrap a derived expression as a hole."""
    first, set_first = create_signal("Ada")
    last, set_last = create_signal("Lovelace")

    return div(
        h3("dynamic(getter)"),
        p("Type below — only the dynamic hole updates."),
        div(
            input_(
                value=first,
                on_input=lambda e: set_first(e.target.value),
                placeholder="First",
                class_="form-input",
            ),
            input_(
                value=last,
                on_input=lambda e: set_last(e.target.value),
                placeholder="Last",
                class_="form-input",
            ),
            class_="form-row",
        ),
        p("Greeting: ", dynamic(lambda: f"Hello, {first()} {last()}!")),
        class_="demo-section",
    )


# --------------------------------------------------------------------------- #
# Demo 3 — reactive props (class, style, attribute)
# --------------------------------------------------------------------------- #


@component
def ReactivePropBindings():
    """Callable prop values become independent reactive bindings."""
    danger, set_danger = create_signal(False)
    color, set_color = create_signal("teal")

    pill_class = create_memo(lambda: "pill danger" if danger() else "pill")

    return div(
        h3("Reactive props"),
        p("Each prop has its own effect — no component re-render."),
        div(
            span("Status", class_=pill_class),
            span("Hello", style=lambda: {"color": color(), "fontWeight": "600"}),
            class_="form-row",
        ),
        div(
            button(
                "Toggle danger",
                on_click=lambda e: set_danger(not danger()),
            ),
            button(
                "Cycle color",
                on_click=lambda e: set_color({"teal": "salmon", "salmon": "gold", "gold": "teal"}.get(color(), "teal")),
            ),
            class_="form-row",
        ),
        class_="demo-section",
    )


# --------------------------------------------------------------------------- #
# Demo 4 — independent updates (each hole has its own effect)
# --------------------------------------------------------------------------- #


@component
def IndependentHoles():
    """Two unrelated holes update without touching each other's effects."""
    a, set_a = create_signal(0)
    b, set_b = create_signal(0)
    a_runs = [0]
    b_runs = [0]

    def get_a():
        a_runs[0] += 1
        return a()

    def get_b():
        b_runs[0] += 1
        return b()

    a_count_sig, set_a_count = create_signal(0)
    b_count_sig, set_b_count = create_signal(0)

    def click_a(_):
        set_a(a() + 1)
        set_a_count(a_runs[0])

    def click_b(_):
        set_b(b() + 1)
        set_b_count(b_runs[0])

    return div(
        h3("Independent holes"),
        p("Each hole has its own effect.  Watch the run counters."),
        div(
            div(
                p("Value A: ", span(get_a, class_="hole-value")),
                p("A hole runs: ", span(a_count_sig)),
                button("A++", on_click=click_a),
            ),
            div(
                p("Value B: ", span(get_b, class_="hole-value")),
                p("B hole runs: ", span(b_count_sig)),
                button("B++", on_click=click_b),
            ),
            class_="form-row",
        ),
        class_="demo-section",
    )


# --------------------------------------------------------------------------- #
# Demo 5 — hole returning a VNode (conditional swap)
# --------------------------------------------------------------------------- #


@component
def NodeHole():
    """A hole can return a different VNode shape on each evaluation."""
    mode, set_mode = create_signal("emphasis")

    def render_word():
        m = mode()
        if m == "emphasis":
            return span("important!", style={"color": "var(--accent)", "fontWeight": "700"})
        if m == "code":
            return code("important!", class_="inline-code")
        return span("important!", style={"color": "var(--text-3)"})

    cycle_map = {"emphasis": "code", "code": "plain", "plain": "emphasis"}

    return div(
        h3("Hole returning VNode"),
        p("This hole returns a different element each time."),
        p("It is ", render_word, "."),
        button(
            "Cycle mode",
            on_click=lambda e: set_mode(cycle_map.get(mode(), "emphasis")),
        ),
        class_="demo-section",
    )


# --------------------------------------------------------------------------- #
# Page
# --------------------------------------------------------------------------- #


_INTRO = """\
A *reactive hole* is a zero-arg callable placed inside a VNode (child
or prop value).  The reconciler wraps each hole in its own effect, so
the component body runs **once** and only the hole's DOM updates when
its dependencies change.

\u2022 Pass a signal accessor: ``span(count)``
\u2022 Pass a derived expression: ``dynamic(lambda: f\"hi {name()}\")``
\u2022 Use it in a prop: ``p(class_=cls)``"""


@component
def Page():
    return div(
        div(
            h2("Reactive Holes"),
            p(
                "Fine-grained reactivity inside the VDOM.  Components run once; holes update independently.",
                class_="page-subtitle",
            ),
            class_="page-header",
        ),
        section(
            pre(code(_INTRO), class_="code-block"),
            class_="code-section",
        ),
        h(TextHole, {}),
        h(DynamicHelper, {}),
        h(ReactivePropBindings, {}),
        h(IndependentHoles, {}),
        h(NodeHole, {}),
        class_="page",
    )
