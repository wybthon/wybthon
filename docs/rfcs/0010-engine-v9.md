# RFC 0010: Engine v9: components and control flow at the cost of their markup, and one-command hydration

- **Status:** Implemented
- **Author:** Owen Carey
- **Created:** 2026-11-07

## Summary

Make the layers applications are built from cost about what the markup inside them costs. Engine v9 changes four things:

1. **Components mount straight into their slot.** A component tag builds its node directly, runs its body once, and mounts the template the body returns in front of the slot's placeholder, without a hole region, a region update, or the general mount dispatch. In a template that's never patched (a component's output, a list row), a child slot holding a list of one node mounts that node, with no fragment.
2. **Regions that fill a slot have no markers.** A `Show`, `Switch`, `For`, `Repeat`, or unkeyed fragment that's a hole's whole content ends at the hole's anchor (the template slot's placeholder) and creates no comment nodes of its own, on the client and on the server.
3. **A template instance hydrates with one command.** The server writes an instance in the layout its clone has, with each slot's content in front of a `<!--$-->` comment where the clone has the slot's placeholder. The kernel claims the whole instance with `CLAIM_TPL`, registering its nodes as a clone would, and the instance's slots fill as they do after a clone.
4. **Plain updates and store rows take shorter paths.** A signal write with no transition, action, or optimistic scope stages without the general write protocol; a template binding's apply stage runs without the publication checks it can't need; `_read` returns plain values and compiler getters without classifying them; and a template expression whose probe found a reactive read isn't probed again for later instances of the template.

The virtual DOM, the batched kernel, the reactive semantics, and the public API stay as they are.

## Motivation

### Solid 2.0 hasn't moved

npm's `latest` is still `solid-js@1.9.18`, and `next` is `2.0.0-rc.21` (November 4), which Wybthon targets. Nothing in Solid's public exports changed between RC.21 and the head of its `next` branch. API parity isn't the gap.

### Components and control flow cost several times their markup

The js-framework-benchmark table, which earlier engines optimized, is a flat template row: one clone command and about 40 Python calls. Applications aren't flat. `benchmarks/component_bench.py` mounts 1,000 rows showing the same markup four ways. On v0.44.0 (CPython 3.14, best of five):

| Row | Create | Calls per row | Commands per row | Bytes per row |
| --- | ---: | ---: | ---: | ---: |
| Inline markup | 2.65 ms | 41 | 1 | 986 |
| Inline markup with a `Show` | 6.20 ms | 97 | 5 | 2,890 |
| The markup in a component | 7.65 ms | 134 | 6 | 3,378 |
| A component with a `Show` | 11.36 ms | 190 | 10 | 5,282 |

A component boundary cost about 93 Python calls and five extra commands: a hole region and a region update around the component, the general mount dispatch, a fragment with two comment markers around a single child, and a hole for the children. A `Show` cost more than the row it sat in, and its two markers were four more commands.

### Hydration sent ten commands per row

Hydrating 1,000 server-rendered rows sent 10 commands per row for the inline markup and 13 for the component, where a client render sends 1 and 6: every template was expanded into VNodes and claimed node by node. Engine v8's RFC left claiming a template instance in one command open because the kernel couldn't tell where a slot's server content ends without markers the server didn't write.

### The core paid for transitions it wasn't in

Engine v8 measured a plain signal write and flush at 2.7 times a 190-line reference implementation, and a store field read at 4.7 times. A store row's field binding read the field twice: its static probe read it, found it reactive, and escaped with an exception, and then the binding read it again.

## Design

### 1. Components

`templates._component` builds an `@component`'s node directly outside dev mode (dev mode still validates the props through the call). A component slot whose node is a component mounts it with `reconciler._region_commit` instead of `_region_set`, and a child slot whose value is a node or a list does the same; under a server render or hydration both keep the general path, which assigns hydration keys.

`reconciler._mount_component` resolves the props class once and builds the props instance without `Component._render`'s tuple, and, when the body returns one template instance that can clone, mounts it with `_clone` (the clone path `_mount_dispatch` and list rows share) and takes the instance's root as the component's first node. `_mount_dispatch` sends a callable tag to `_mount_component` before comparing it with the string tags. `templates.mount`, which nothing calls any more, is removed.

A list in a child slot mounts as a fragment, which is anchored there (see below), so it has no markers. In a template instance that's never patched (a component's output, a list row, a branch's content), a list of one node mounts as that node instead: no later list is ever compared with it. Everywhere else, including `_coerce_result` and so every hole's result, a list stays a fragment, even a list of one. A keyed list that grows from one item to two then reconciles against the fragment instead of replacing its item, and a node a component received in `children` and mounts again (a `Show` that reopens over `props.children`) keeps the values a final mount would release. A server render and hydration take the fragment path, which writes the same DOM.

A component tag's attributes are converted to prop names once per tag (`_Component.props`), not per instance.

### 2. Anchored regions

`reconciler._mount_in_region`, which mounts a hole's content (on the client and while hydrating), marks a `_branch`, `_list`, or unkeyed `_fragment` without a `marker` as *anchored*: `_open_fragment` gives it the hole's anchor as both its start and its end and creates (or claims) nothing. Content mounts in front of the anchor, as a region's content always did.

The position helpers read the VNode tree, as before. `_first_dom_id` of an anchored region is its first child's first node (the anchor when it's empty); the new `_last_dom_id` is its last child's last node (`None` when it's empty); `_range_bounds` combines them; `_dom_node_ids` leaves the anchor out. Unmounting, moving, and parking an anchored region therefore touch only its content, never the hole's anchor.

A keyed fragment keeps its markers, as it does among an element's children, so a template slot holding one mounts the same DOM as the tree the template stands for.

The server renderer writes a hole's whole content without the region's markers (`dispatch(..., anchored=True)`).

### 3. Hydration by claim

**Which templates.** `_Compiled.claimable` is set when a template has no SVG or MathML names the parser would change case of, no spreads, no inner-HTML props, and none of the elements the server writes by its general path (raw text, a leading newline, `select`, `option`, `optgroup`, `svg`, `math`). An instance of a claimable template under an HTML parent hydrates by claim; any other expands and claims node by node, as before.

**The server's layout.** `Renderer.claimed` writes the template's markup with the instance's attributes, and for each slot, in the template's order:

- a text slot (one the clone holds as a text node) showing text writes that text, escaped, and nothing else;
- any other child slot, and every component slot, writes its content followed by `<!--$-->`.

The content of slot `k` of an instance at position `p` is rendered at position `p.k`: a component's scope, a hole's expression (`p.kh`, or `p.k` for a text slot's expression), and the content's own position (`p.k.h`) match what the client computes. `NoHydration` content is never claimed, so templates inside it are written without placeholders.

**The kernel.** `CLAIM_TPL [first, tpl, parent, anchor, *hints, writes?]` takes the next element under the parent's claim cursor as the instance's root and walks the template's prototype against the server's nodes, numbering them in the pre-order a clone uses and registering the addressed ones. Static text is claimed with the split that merged text needs. A text slot whose hint is a string claims that text (an empty one is created); a comment slot, and a text slot whose hint is `0`, scans forward for the `$` comment, records the first node in front of it as the slot's content start, registers the comment as the slot's node, and empties its data so the DOM reads as a clone's. Every claimed node is kept at the end of hydration. A server node that doesn't match is a mismatch: the prototype's subtree is cloned in its place and registered as a clone would be, with its slots empty. Delegated listener types are marked as a clone marks them. When present, `writes` holds the instance's `SET_ATTR` and `SET_STYLE` commands; after the walk, the kernel applies each one whose value differs from what the server wrote, and a `SET_STYLE` whose fourth field is set first removes the server's other declarations.

`CLAIM_SLOT [parent, slot]` points the slot's parent's claim cursor at the content start `CLAIM_TPL` recorded; `reconciler._region_commit` sends it while hydrating, before a slot's content mounts, so only slots that hold nodes cost a command. `HOLE_TEXT`, while hydrating, adopts the server's text in front of a slot's placeholder (and removes the placeholder) instead of replacing the placeholder with new text.

**The client.** `templates.claim` is the generic counterpart of a generated mount function: it allocates the instance's ids, sends `CLAIM_TPL` with each text slot's hint (a literal's text at once, an expression's when its binding first applies, through the same `_fill` that fills a clone's text, and `0` when a text slot turns out to hold nodes), and fills each slot with the same slot functions a clone uses, positioned at `p.k`. The attribute and style writes the first render makes go into the claim command's `writes` instead of commands of their own, so a value only the browser computes (a stored theme, the user's language) is still corrected without costing a command. The first value decides the attribute whole, as the server's value did: a style slot's declarations are merged into one `SET_STYLE` that replaces the server's style, and an attribute slot whose first value leaves the attribute out (`None`, `False`) adds a removal (`_dom_props.claimed_attribute` names the attribute). A slot whose value is still loading writes nothing, so the server's value stays until it arrives. `_mount_dispatch` routes a claimable template to it while claiming.

The JavaScript kernel and the Python reference backend implement both commands; `tests/test_ssr_output.py` now also hydrates every view whose markup the in-memory parser reads as a browser does and requires zero mismatches.

### 4. Core and stores

- **Plain writes.** `Signal.set`, outside an action, an optimistic scope, an apply stage, a held transition, and an eager flush-time computation, stages the write in straight-line code, comparing values with `_changed` as `_set` does: the origin is normal and no transition can claim it.
- **Binding applies.** `Computation._run_apply` runs a template binding's module apply stage directly when the binding has no extension record, no unpublished preparation, and a settled value.
- **`_read`.** A plain value (text, a number, a container, `None`) returns at once, and a compiler getter calls its expression without the accessor rule.
- **`_probe_target`.** A probe's synchronous result type returns as static without the accessor rule. A probe that escapes (found a reactive read, created something, or raised) marks the expression's code object; later probes of a marked expression return it unprobed, so its binding becomes a computation at once. A binding of a marked expression that returns an accessor, or that reads nothing reactive, unmarks it, so the probe's two optimizations (binding to a handed-over accessor, and allocating nothing for a static value) still apply. The set is bounded, and a hot update clears it, so replaced code isn't kept alive.

## Breaking changes

| Removed or changed | Replacement |
| --- | --- |
| A server-rendered template instance had no slot placeholders | Each child or component slot's content is followed by `<!--$-->`, where the clone has the slot's placeholder; a text slot showing text is that text alone |
| A `Show`, `For`, `Repeat`, `Switch`, or unkeyed fragment that's a hole's whole content sat between two comment markers | It ends at the hole's anchor and has no markers, in the browser and in server output |
| A list of one node in a child slot of a component's output or a list row mounted as a fragment between two markers | It mounts as that node |
| Hydration keys of content inside a template slot were positioned by child index (`p.i`) | By the slot's index in the template's plan (`p.k`); server and client of the same version agree |
| Server output of a template matched the `h()` tree it stands for byte for byte | It matches once comment markers are ignored |
| Kernel commands 1 to 29 | Adds `CLAIM_TPL` (30), which carries the instance's attribute writes, and `CLAIM_SLOT` (31); `HOLE_TEXT` adopts server text while hydrating |
| The kernel documentation listed `REMOVE` (removed in Engine v8) | Removed from the documentation |

## Alternatives considered

**Splitting transitions, async, and probes into an overlay the plain signal graph never consults.** It's still the core's next step, and the 3,200 tests that pin the transition engine's semantics make it safer than it was. But mounting components, regions, and hydrated pages was where applications paid, and the fast paths above take most of the cost out of plain writes without touching the transition engine.

**Start markers for slot content instead of a `$` placeholder after it.** Either marks the slot's extent for the kernel. A placeholder after the content is the node the clone already has, so a hydrated instance is the same DOM as a cloned one and the hole's anchor needs no special case.

**Hints for comment slots too, so text next to static text needs no placeholder.** The kernel would need every comment slot's text before the instance's slots fill. `HOLE_TEXT` adopting the server's text gives the same DOM without a second hint table.

**Recognizing `Show`, `For`, and the other flow controls in the compiler.** It would remove the run-time check in `_compiled.call` and its two closures at each call site, about two calls per instance. Small, and it needs the compiler to resolve imports; left for later.

**Rendering `Show`'s children lazily.** Solid evaluates a branch's JSX only when the branch shows. Wybthon builds the children's template node when `Show` is called (no DOM, no bindings), which is cheap, and changing it changes when nested calls in the children run.

## Drawbacks and risks

- **Server HTML has more comments.** A comment slot holding text (`Count: {count}!`) is now followed by `<!--$-->`. After hydration, the comment is gone (its text was adopted) or empty, as a clone's placeholder is.
- **Two hydration paths.** Templates the server writes by its general path still claim node by node, so both paths stay tested: the browser suite, `tests/test_ssr.py`, `tests/test_ssr_output.py`, and `tests/test_engine_v9.py` cover each.
- **The claim command carries the attribute values.** A claimed instance sends its dynamic attribute and style values inside `CLAIM_TPL`, and the kernel compares each with the server's before writing it, so the command grows with the instance's dynamic attributes.
- **A learned probe can cost an allocation.** An expression whose probe escaped in one instance binds as a computation in the next, even if that instance's value is static; the binding is then dropped at once and the mark cleared.

## Testing

- The unit suite (3,241 tests), including `tests/test_engine_v9.py`: commands per component row, marker-free `Show` and `For` in slots, a hole switching between anchored regions and text, one `CLAIM_TPL` per instance and one `CLAIM_SLOT` per slot holding nodes, attribute values only the browser computes corrected through the claim, text adoption next to static text, a mismatched instance rebuilt in place, hydrated DOM against a client render, `NoHydration` without placeholders, the learned probe, a `Show` reopening over `props.children`, and a keyed list keeping its item through a length of one.
- `tests/test_ssr_output.py` hydrates its views and requires zero mismatches.
- The browser suite (95 tests in Chromium on Pyodide 314.0.6), including the full-stack and hydration tests, which run the JavaScript kernel's `CLAIM_TPL` walk and its attribute writes.
- `benchmarks/component_bench.py` (new), `benchmarks/row_bench.py`, and `benchmarks/compare_browser.py` with a new `component` mode in the benchmark app, against v0.44.0.

## Results

See [Engine v9 benchmark results](https://github.com/wybthon/wybthon/blob/main/benchmarks/results/engine-v9.md).

## Unresolved questions

- The overlay split for the reactive core.
- Claiming SVG, `select`, and raw-text templates in one command.
- Recognizing flow controls in the compiler, and lazy `Show` children.
- A store row still costs about one and a half times a row of per-row signals to create.
- On the general hydration path (templates claimed node by node), an attribute the server wrote but the browser computes as `None` stays, as a binding's first apply removes nothing from a fresh element; a claimed instance removes it. On both paths, a `dataset` key only the server wrote stays.

## Decision

Accepted on 2026-11-07. Wybthon is pre-1.0 and has no production users yet, so the changes ship without a compatibility layer.
