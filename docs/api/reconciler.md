### wybthon.reconciler

::: wybthon.reconciler

#### What's in this module

The reconciler walks a previous and next VDOM tree and applies the
minimal set of DOM mutations to bring the page into sync. It handles
keyed lists, fragments, components, text nodes, and reactive holes.

Most users never call into this module directly. [`render`][wybthon.render]
mounts a tree and the reconciler kicks in for subsequent updates. Read
this page if you're contributing to Wybthon, debugging a diffing bug, or
curious how holes plug into the patching loop.

#### Key responsibilities

| Concern | How the reconciler handles it |
| --- | --- |
| Mounting | Static subtrees mount through the [`template`][wybthon.template] fast path: one `innerHTML` parse plus a wiring pass, instead of one FFI call per node. |
| Element diffing | Matches by `tag`. If tags differ, the old subtree unmounts. |
| Children | A three-pass O(n) match (identity, then key, then type) with a longest-increasing-subsequence move pass keeps DOM moves minimal. |
| Components | A component's body runs once; the reconciler updates props on the existing component instance. |
| Reactive holes | Each hole is an effect; the reconciler patches only the affected node when the signal updates. |
| Cleanup | Unmounting a node disposes the corresponding owner, recursively. |

#### See also

- [`template`][wybthon.template]: the template-based mounting fast path.
- [`vnode`][wybthon.vnode]: the data structure being diffed.
- [Concepts: Virtual DOM](../concepts/vdom.md)
- [Concepts: Lifecycle and Ownership](../concepts/lifecycle.md)
