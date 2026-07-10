### wybthon.reconciler

::: wybthon.reconciler

#### What's in this module

The reconciler walks a previous and next VDOM tree and emits the
minimal set of DOM operations to bring the page into sync. It never
touches the DOM directly: every mutation is a compact op against an
integer node id (see `wybthon.kernel`), applied in one bridge crossing
per commit. It handles keyed lists, fragments, components, text nodes,
and reactive holes.

Most users never call into this module directly. [`render`][wybthon.render]
mounts a tree and the reconciler kicks in for subsequent updates. Read
this page if you're contributing to Wybthon, debugging a diffing bug, or
curious how holes plug into the patching loop.

#### Key responsibilities

| Concern | How the reconciler handles it |
| --- | --- |
| Mounting | Static subtrees mount through the [`template`][wybthon.template] fast path: one clone op per mount of a registered skeleton, instead of one op per node. |
| Element diffing | Matches by `tag`. If tags differ, the old subtree unmounts. |
| Children | A three-pass O(n) match (identity, then key, then type) with a longest-increasing-subsequence move pass keeps DOM moves minimal. |
| Components | A component's body runs once; the reconciler updates props on the existing component instance. |
| Reactive holes | Each hole is an effect; the reconciler patches only the affected region when the signal updates. |
| Cleanup | Unmounting disposes the owner recursively and retires the whole subtree with one `REMOVE` per top-level node plus one `RELEASE` op. |

#### See also

- [`template`][wybthon.template]: the template-based mounting fast path.
- [`vnode`][wybthon.vnode]: the data structure being diffed.
- [Concepts: Virtual DOM](../concepts/vdom.md)
- [Concepts: Lifecycle and Ownership](../concepts/lifecycle.md)
