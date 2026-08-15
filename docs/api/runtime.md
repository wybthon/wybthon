### wybthon.runtime

::: wybthon.runtime

#### What's in this module

`runtime` defines the public lifetime boundary for rendered applications.
[`render`][wybthon.render] uses a default runtime, while
[`create_runtime`][wybthon.create_runtime] creates an isolated runtime for
tests, embedded widgets, or multiple documents.

`Runtime.render(vnode, container)` returns a `MountHandle`. Rendering into
the same container through the same runtime patches the existing handle.
`handle.update(vnode)` performs the same update directly, and
`handle.dispose()` unmounts the DOM, cancels owned async tasks, disposes
reactive owners, and removes the handle from the runtime.

`Runtime.stats()` reports live mount, mounted-node, owner, and task counts.
It's intended for diagnostics, leak tests, and benchmark assertions.

#### See also

- [Concepts: Runtime and Mounts](../concepts/runtime.md)
- [`reconciler`][wybthon.reconciler]: internal mounted-tree reconciliation.
- [`vnode`][wybthon.vnode]: reusable render declarations.
