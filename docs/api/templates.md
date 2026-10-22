### wybthon.templates

::: wybthon.templates
    options:
      members:
        - html
        - TemplateError

#### What's in this module

`templates` turns t-string HTML templates into nodes. The [compiler](compiler.md) parses and validates each literal when its module is compiled, turns its dynamic interpolations into getters, and emits its mount functions as ordinary module code, so `html()` only rebuilds the slot plan from the precompiled tree on first use. A template that reaches `html()` uncompiled (a REPL, `exec`) is parsed and compiled on its first call instead, keyed by the identity of its static strings. See [Templates](../concepts/templates.md) for the full guide.

| Name | Description |
| --- | --- |
| [`html`][wybthon.html] | Turn a t-string template into a node. |
| [`TemplateError`][wybthon.TemplateError] | Raised for malformed markup, markup the HTML parser would rewrite, or, in dev mode, an uncompiled template whose dynamic expression was evaluated once. |

#### See also

- [Compiler](compiler.md): what happens to each interpolation, and where templates are compiled.
- [VNode](vnode.md): the node type templates produce, and `h()`, the programmatic layer.
