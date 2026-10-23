"""Components: reactive props (no remount), refs, children, lifecycle."""

from typing import Any

from wybthon import (
    ParentProps,
    Props,
    Ref,
    Show,
    component,
    create_signal,
    html,
    on_cleanup,
    on_settled,
)


class DisplayProps(Props):
    text: str = ""


class FancyProps(Props):
    # A plain field: the ref object is handed through untouched.
    ref: Any = None


@component
def Fancy(props: FancyProps):
    # Refs pass through like any other plain field; no forward_ref needed.
    return html(t'<input type="text" ref={props.ref} data-testid="comp-ref-input">')


@component
def Card(props: ParentProps):
    return html(t"""
      <div data-testid="comp-card"><span data-testid="comp-card-label">card:</span>{props.children}</div>
    """)


@component
def Page():
    label, set_label = create_signal("hello")
    display_mounts, set_display_mounts = create_signal(0)

    @component
    def Display(props: DisplayProps):
        on_settled(lambda: set_display_mounts(lambda n: n + 1))
        return html(t'<span data-testid="comp-display">{props.text}</span>')

    input_ref = Ref()
    ref_attached, set_ref_attached = create_signal(False)
    on_settled(lambda: set_ref_attached(input_ref.current is not None))

    shown, set_shown = create_signal(True)
    life_mounts, set_life_mounts = create_signal(0)
    life_cleanups, set_life_cleanups = create_signal(0)

    @component
    def Lifecycle():
        on_settled(lambda: set_life_mounts(lambda n: n + 1))
        on_cleanup(lambda: set_life_cleanups(lambda n: n + 1))
        return html(t'<span data-testid="comp-life">alive</span>')

    def toggle_life():
        set_shown(lambda v: not v)

    # `label()` is compiled into a getter: Display reads it through its
    # props, so a new label updates the mounted instance in place.
    return html(t"""
      <div data-testid="page-components">
        <h2>Components</h2>
        <div>
          <{Display} text={label()} />
          <span data-testid="comp-display-mounts">{display_mounts()}</span>
          <button data-testid="comp-label-btn" onclick={(lambda: set_label("world"))}>change label</button>
        </div>
        <div>
          <{Fancy} ref={input_ref} />
          <span data-testid="comp-ref-attached">{"yes" if ref_attached() else "no"}</span>
        </div>
        <div><{Card}><span data-testid="comp-card-child">inside</span></{Card}></div>
        <div>
          <button data-testid="comp-life-toggle" onclick={toggle_life}>toggle life</button>
          {Show(shown(), html(t"<{Lifecycle} />"))}
          <p>
            mounts: <span data-testid="comp-life-mounts">{life_mounts()}</span>{" "}
            cleanups: <span data-testid="comp-life-cleanups">{life_cleanups()}</span>
          </p>
        </div>
      </div>
    """)
