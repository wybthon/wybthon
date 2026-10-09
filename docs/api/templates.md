### wybthon.templates

::: wybthon.templates
    options:
      members:
        - html
        - TemplateError

#### What's in this module

`templates` compiles t-string HTML templates. Each literal is parsed and compiled once, keyed by the identity of its static strings; every later call only supplies the interpolated values. See [Templates](../concepts/templates.md) for the full guide.

| Name | Description |
| --- | --- |
| [`html`][wybthon.html] | Turn a t-string template into a node. |
| [`TemplateError`][wybthon.TemplateError] | Raised for malformed markup, or markup the HTML parser would rewrite. |

#### See also

- [Element helpers](elements.md): the programmatic layer for building nodes.
- [VNode](vnode.md): the node type templates and helpers produce.
