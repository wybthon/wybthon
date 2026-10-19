"""Compiled t-string templates (`html`) in the real browser parser and kernel."""

from wybthon import For, ParentProps, Prop, Show, component, create_memo, create_signal, html


class CardProps(ParentProps):
    title: Prop[str]


@component
def Card(props: CardProps):
    return html(t'<section class="tpl-card" data-testid="tpl-card"><h3>{props.title}</h3>{props.children}</section>')


@component
def Page():
    count, set_count = create_signal(0)
    kind, set_kind = create_signal("primary")
    name, set_name = create_signal("Ada")
    rows, set_rows = create_signal([{"id": i, "label": create_signal(f"row {i}")} for i in range(3)])
    shown, set_shown = create_signal(False)
    spellings, set_spellings = create_signal("")
    doubled = create_memo(lambda: count() * 2)

    def increment():
        set_count(lambda n: n + 1)

    def toggle_kind():
        set_kind(lambda k: "danger" if k == "primary" else "primary")

    def add_row():
        set_rows(lambda rs: [*rs, {"id": len(rs), "label": create_signal(f"row {len(rs)}")}])

    def relabel_first():
        rows.peek()[0]["label"][1]("first!")

    def heard(which):
        return lambda: set_spellings(lambda s: s + which)

    def row(item, index):
        return html(t'<tr data-testid="tpl-row"><td>{item["id"]}</td><td>{item["label"][0]}</td></tr>')

    def badge():
        return html(t'<b data-testid="tpl-badge" title={f"n={count()}"}>{count() * 10}</b>')

    return html(t"""
      <div data-testid="page-templates">
        <h2>Templates</h2>
        <p data-testid="tpl-count">Count: {count} (doubled: {doubled})</p>
        <button data-testid="tpl-inc" onclick={increment}>+1</button>
        <button data-testid="tpl-kind" class="btn btn-{kind}" onclick={toggle_kind}>kind</button>
        <p data-testid="tpl-whitespace">
          one
          two   three
        </p>
        <input data-testid="tpl-name" value={name} oninput={(lambda e: set_name(e.target.value))}>
        <p data-testid="tpl-greeting">Hello, {name}!</p>
        <table>
          <tbody data-testid="tpl-body">{For(rows, row)}</tbody>
        </table>
        <button data-testid="tpl-add" onclick={add_row}>add</button>
        <button data-testid="tpl-relabel" onclick={relabel_first}>relabel</button>
        <div data-testid="tpl-patched">{badge}</div>
        <{Card} title="Card"><em data-testid="tpl-card-child">child {count}</em></{Card}>
        <button data-testid="tpl-show" onclick={(lambda: set_shown(lambda v: not v))}>show</button>
        {Show(shown, html(t'<i data-testid="tpl-shown">shown</i>'), html(t'<i data-testid="tpl-hidden">hidden</i>'))}
        <button data-testid="tpl-lower" onclick={heard("a")}>a</button>
        <button data-testid="tpl-camel" onClick={heard("b")}>b</button>
        <button data-testid="tpl-colon" on:click={heard("c")}>c</button>
        <span data-testid="tpl-heard">{spellings}</span>
        <svg data-testid="tpl-svg" viewBox="0 0 10 10"><circle r={count} cx="5" cy="5" /></svg>
      </div>
    """)
