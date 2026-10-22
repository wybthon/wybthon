### wybthon.compiler

::: wybthon.compiler

#### What's in this module

`compiler` is Wybthon's compile step, the counterpart of Solid's JSX
compiler, done on Python's syntax tree. It rewrites every
`html(t"...")` call whose argument is a t-string literal: each dynamic
interpolation (one containing a call, an attribute access, or a
subscript) becomes a getter, a call in a child position is dispatched
to a component or made a reactive hole, and the literal's parse tree and
mount functions are emitted as ordinary module code. Nothing else in the
module changes. See [Concepts: Compiler](../concepts/compiler.md) for
the rules and how to inspect the output.

You rarely call it directly. It runs in `wyb build` and `wyb dev`, in
the import hook that `import wybthon` installs, in the pytest plugin,
and in `wyb run script.py`.

| Name | Description |
| --- | --- |
| [`install`][wybthon.compiler.install] | Install the import hook (idempotent); `import wybthon` calls it. |
| [`uninstall`][wybthon.compiler.uninstall] | Remove the import hook. |
| [`compile_source`][wybthon.compiler.compile_source] | `compile_source(source, filename)`: a module's code object with its templates compiled, ready for `exec`. |
| [`transform`][wybthon.compiler.transform] | `transform(tree, filename="<unknown>", source="")`: rewrite a module's `ast` in place and return it; raises `SyntaxError` for a malformed template. |
| [`is_dynamic`][wybthon.compiler.is_dynamic] | Whether an expression node contains a call, attribute access, or subscript (outside the lambdas inside it). |
| [`is_candidate`][wybthon.compiler.is_candidate] | Whether a module's source bytes might hold `html(t"...")` calls: it mentions `wybthon` and `html` and contains a t-string. |
| [`defers`][wybthon.compiler.defers] | Whether the compiler would defer an interpolation's source text in a given position; `html()` uses it for the dev-mode check of uncompiled templates. |
| `COMPILER_TAG` | The optimization tag of cached compiled bytecode (`*.opt-wyb1.pyc`); it changes when the compiler's output does. |

```python
from wybthon.compiler import compile_source

source = """
from wybthon import create_signal, html

count, set_count = create_signal(2)
view = html(t"<p>{count() * 2}</p>")
"""

namespace = {}
exec(compile_source(source, "generated.py"), namespace)  # {count() * 2} is a reactive hole
```

- `html` is resolved through the module's imports (`from wybthon import
  html`, `from wybthon.templates import html`, an alias of either, or
  `wybthon.html`), so a module that defines its own `html` is left
  alone.
- A malformed template is a `SyntaxError` with its file and line when the
  module is compiled, not a [`TemplateError`][wybthon.TemplateError] at
  run time.
- The generated names (`__wybthon__`, `__wybthon_t0__`,
  `__wybthon_m0__`) are dunder names, which Python never mangles inside
  classes.

#### See also

- [Concepts: Compiler](../concepts/compiler.md)
- [Templates](templates.md): what `html()` does with a compiled literal
- [Dev server (CLI)](dev.md): `wyb build`, `wyb dev`, and `wyb run`
- [Guides: Testing](../guides/testing.md): the pytest plugin
- [RFC 0004: Engine v4](../rfcs/0004-engine-v4.md)
