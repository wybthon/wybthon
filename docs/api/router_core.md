### wybthon.router_core

::: wybthon.router_core

#### What's in this module

`router_core` contains the *browser-agnostic* path matching engine used
by [`wybthon.router`][wybthon.router]. It exposes:

- [`RouteSpec`][wybthon.router_core.RouteSpec]: a normalized route
  description used internally by `Route`.
- [`resolve`][wybthon.router_core.resolve]: match a path against a list
  of route specs and return the matched chain plus extracted params.

You don't usually call this module directly. Write [`Route`][wybthon.Route]
declarations and let [`Router`][wybthon.Router] resolve them. Use
`router_core` if you need to test routing logic outside a browser
environment or build custom navigation tooling.

#### Path patterns

| Pattern | Matches | Notes |
| --- | --- | --- |
| `/users` | `/users` | Static segment. |
| `/users/:id` | `/users/42` | `:id` becomes a string param. |
| `/files/*splat` | `/files/a/b/c` | Splat captures the remainder as a single string. |
| `/(public|private)` | `/public` or `/private` | Alternation works in the underlying regex. |

Param values are URL-decoded before being passed to components.

#### See also

- [`router`][wybthon.router]: the browser-side router and components.
- [Concepts: Router](../concepts/router.md)
- [Examples: Router](../examples/router.md)
