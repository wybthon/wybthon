### wybthon.testing

::: wybthon.testing

#### What's in this module

`wybthon.testing` renders components in plain CPython, through the real
reconciler, kernel protocol, scheduler, and event delegation, into an
in-memory DOM. Nothing is mocked, so a passing test exercises the same
commands the browser kernel applies. The queries follow Testing
Library's conventions.

| Name | Description |
| --- | --- |
| [`render`][wybthon.testing.render] | `render(view) -> Screen`: mount a view (a VNode or a zero-arg callable) into a fresh in-memory document. |
| [`Screen`][wybthon.testing.Screen] | Queries plus `html()`, `text()`, and `unmount()`; also a context manager that unmounts on exit. |
| [`fire`][wybthon.testing.fire] | Dispatch events through delegated handlers and flush: `fire.click(node)`, `fire.input(node, value)`, `fire.change(node, value=None, checked=None)`, `fire.submit(form)`, `fire.key_down(node, key)`, `fire.focus(node)`, `fire.blur(node)`, or `fire(node, "dblclick", **payload)`. |
| [`cleanup`][wybthon.testing.cleanup] | Unmount everything `render` mounted; call it after each test, or from an autouse fixture. |
| [`TestNode`][wybthon.testing.TestNode], [`TestDocument`][wybthon.testing.TestDocument] | The in-memory DOM the screen renders into. |
| [`reactive_scope`][wybthon.testing.reactive_scope], [`tick`][wybthon.testing.tick], [`wait_for`][wybthon.testing.wait_for] | Helpers for testing reactive code and async updates outside a component. |

| Query | Finds | Variants |
| --- | --- | --- |
| `get_by_text(text, *, exact=True)` | Elements by visible text, or a compiled regex | `query_by_text`, `get_all_by_text` |
| `get_by_role(role, *, name=None)` | Elements by ARIA role and accessible name | `query_by_role`, `get_all_by_role` |
| `get_by_label_text(text)` | Form controls by their label | `query_by_label_text` |
| `get_by_test_id(test_id)` | Elements by `data-testid` | `query_by_test_id`, `get_all_by_test_id` |

`get_by_*` raises unless exactly one element matches, `query_by_*`
returns the match or `None`, and `get_all_by_*` returns every match.

```python
import pytest

from wybthon import Prop, Props, component, create_signal, html, prop
from wybthon.testing import cleanup, fire, render


class CounterProps(Props):
    label: Prop[str] = prop(default="Count")


@component
def Counter(props: CounterProps):
    count, set_count = create_signal(0)

    def increment():
        set_count(lambda n: n + 1)

    return html(t"<div><p>{props.label}: {count}</p><button onclick={increment}>+</button></div>")


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    cleanup()


def test_counter():
    screen = render(Counter(label="Clicks"))
    fire.click(screen.get_by_role("button", name="+"))
    assert screen.get_by_text("Clicks: 1")
    assert screen.html() == "<div><p>Clicks: 1</p><button>+</button></div>"
```

#### See also

- [Guides: Testing](../guides/testing.md)
- [Kernel](kernel.md): the `PythonBackend` the screen renders through
- [Events](events.md): the delegated handlers `fire` dispatches to
