# RFCs

A request for comments (RFC) is a design document for a large or cross-cutting change to Wybthon. RFCs record what we decided, why we decided it, and what we considered instead, so the reasoning behind the framework's shape outlives the pull request that implemented it.

## When to write an RFC

Write an RFC before you start on a change that does any of the following:

- adds, removes, or renames public API in a way that changes how applications are written;
- changes a runtime contract (reactive semantics, ownership, scheduling, the kernel wire protocol, or the build output);
- adds a new subsystem or a new deployment mode;
- touches several modules at once and would be hard to review without a written design.

Bug fixes, documentation improvements, performance work that preserves behavior, and small additive helpers don't need an RFC. When in doubt, open an issue and ask.

## Process

1. **Draft.** Copy [`0000-template.md`](0000-template.md) to `NNNN-short-title.md`, using the next free number, and fill it in. Open a pull request that adds the file with the status `Draft`. Discussion happens on that pull request.
2. **Decide.** A maintainer sets the status to `Accepted` or `Rejected`, recording the decision and its reasoning in the RFC's "Decision" section. Rejected RFCs stay in the repository; the reasoning is useful later.
3. **Implement.** The implementation may land in the same pull request as the RFC or in later ones. The RFC doesn't need to link them; each squash-merge commit records its pull request, so `git log -- docs/rfcs/NNNN-*.md` finds the history.
4. **Close out.** The pull request that completes the implementation also sets the status to `Implemented`, so the status is correct the moment it merges. Every merge to `main` is released automatically, and the changelog records which release it's in. If later work replaces the design, set the status to `Superseded` and link the new RFC.

An RFC's author may set the status to `Withdrawn` at any point before it's accepted.

While Wybthon is pre-1.0, an RFC may choose breaking changes without a compatibility layer. When it does, it must list every removed or renamed API in its "Breaking changes" section so the migration notes can be written from it.

## Statuses

| Status | Meaning |
| --- | --- |
| Draft | Open for discussion; nothing is decided. |
| Accepted | Approved; implementation may be in progress. |
| Implemented | Fully implemented and merged to `main`. |
| Rejected | Declined; the RFC records why. |
| Withdrawn | Abandoned by its author before a decision. |
| Superseded | Replaced by a later RFC. |

## Index

| RFC | Title | Status |
| --- | --- | --- |
| [0001](0001-server-rendering-and-hydration.md) | Server rendering, hydration, and the boot pipeline | Implemented |
| [0002](0002-engine-v2.md) | Engine v2: compiled mounting, typed props, and Solid 2.0 RC.14 alignment | Implemented |
| [0003](0003-engine-v3.md) | Engine v3: compiled t-string templates and zero-cost components | Implemented |
