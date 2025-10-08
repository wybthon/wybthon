### Roadmap

Wybthon v0.3.0 is published. Below is a prioritized implementation plan to evolve Wybthon into a practical CSR/SPA framework running client-side Python via Pyodide. This plan includes a numbered list of top tasks and versioned milestones up to v1.0.0.

#### Prioritized implementation tasks (top to bottom)

1. Stabilize reactivity scheduling and effect/resource lifecycle
  - Make microtask scheduling deterministic in Pyodide; ensure `_schedule_flush()` is robust and test-covered.
  - Guarantee `Computation.dispose()` consistently unsubscribes and cancels pending runs.
  - Resource cancellation: ensure `Resource.cancel()` reliably aborts JS fetches and Python tasks; add race tests.
2. Document component authoring patterns (function vs class)
  - Authoritative guidance on using `signal`, `computed`, `effect` inside class and function components.
  - Patterns for state ownership, passing `children`, cleanup via `on_cleanup` and effect disposal.
3. Router: nested routes, wildcards, and route info
  - Implement nested route resolution using `Route.children` with params/queries threaded through.
  - Wildcard routes, 404 handling, and base path support.
  - Add `Link` active state styling and `navigate` options.
4. Code splitting and lazy routes (Pyodide-safe)
  - Provide `lazy()` utility for deferred component loading via `importlib`/`micropip` in Pyodide.
  - Example: split demo routes; preloading hooks.
5. Error boundaries ergonomics and loading fallbacks
  - Improve `ErrorBoundary` reset behavior; document guarantees and limitations.
  - Introduce `Suspense`-like helper for `use_resource` loading fallbacks.
6. DOM/VDOM diffing correctness and performance pass
  - Strengthen keyed diffing for reorders; add benchmarks for list ops and text updates.
  - Ensure `_apply_props` covers edge-case removals for `style`, `dataset`, `value`, `checked`.
7. Events: ergonomics and normalization
  - Finalize `DomEvent` docs (`prevent_default`, `stop_propagation`, `current_target`).
  - Normalize `on_foo`/`onFoo` mapping with tests; ensure delegation cleanup on unmount.
8. Forms: bindings and validation completeness
  - Ship and document `bind_checkbox`, `bind_select`, `on_submit` end-to-end; add form-level validation helpers.
  - Accessibility guidance and examples.
9. Dev server quality-of-life
  - Auto-open, configurable static roots, logging, and error overlay for Python exceptions in Pyodide.
  - Cache-busting and content hashing for example demos.
10. Testing matrix and CI
  - Unit tests for router resolution (params, wildcards, nested), VDOM diffing, events delegation, and resources.
  - Pyodide-in-browser smoke tests via Playwright or Pyodide headless.
11. Public API hardening and typing
  - Tighten `__all__` surface, finalize names, improve type hints, and add `typing` docs.
12. CLI scaffolding (research → MVP)
  - `wyb new` to scaffold a Pyodide app with router, components, and dev server config.
  - Templates for basic SPA and demo.

> These tasks map directly into the versioned milestones below.

#### Versioned milestones

- v0.1.1 (Stability and docs)
  - (1) Reactivity flush determinism; resource cancellation tests; minor bug fixes in `_apply_props`.
  - (2) Initial authoring patterns guide with examples (function + class components).
  - (7) Document events and `DomEvent` shape; add basic event tests.
  - (10) CI for unit tests on Python-side; begin Pyodide test harness setup.

- v0.2.0 (Routing foundations)
  - (3) Nested routing with `Route.children`, wildcard routes, 404 handling, base path.
  - (3) `Link` active class and `navigate(replace=True)` examples.
  - (10) Router unit tests covering params, nested, wildcard.
  - Docs: concepts + examples for router, including migration notes.

- v0.3.0 (Lazy loading and code splitting)
  - (4) `lazy()`/`load_component()` utilities compatible with Pyodide; preload APIs.
  - (4) Demo: split `examples/demo` routes; document caveats with Pyodide module loading.
  - (5) Optional `Suspense`-like helper for resource loading fallbacks.

- v0.4.0 (Error handling and UX)
  - (5) ErrorBoundary reset API clarified; fallback ergonomics improved; docs and examples.
  - (7) Event delegation cleanup guarantees on unmount with tests.
  - (8) Form submit patterns with validation aggregates and accessibility tips.

- v0.5.0 (VDOM performance and correctness)
  - (6) Keyed children reorder correctness and micro-benchmarks.
  - (6) Prop application edge cases (style/dataset/value/checked) covered with tests.
  - (10) Add VDOM diffing tests for text node fast-path and reorders.

- v0.6.0 (Dev server DX)
  - (9) Auto-open, static mount configuration, error overlay in browser for Python exceptions.
  - (9) Cache busting for demo assets, configurable host/port messages.
  - Docs: dev server advanced usage and troubleshooting.

- v0.7.0 (API hardening and typing)
  - (11) Finalize public API surface via `__all__` and docs; strengthen type hints.
  - (2) Complete component authoring patterns (state, children composition, cleanup) with larger examples.
  - (10) Expand CI: mypy, formatting, and coverage gates.

- v0.8.0 (Ecosystem and forms)
  - (8) Form-level validation helpers, schema integration option, more bindings examples.
  - (7) Event docs: comprehensive list and cross-browser notes for Pyodide.
  - (10) Add forms and events test suites.

- v0.9.0 (Code splitting + router integration)
  - (4) Route-level code splitting patterns with preloading and error/timeout fallbacks.
  - (3) Router devtools-friendly logging and navigation hooks.
  - Docs: performance guide and code splitting best practices under Pyodide constraints.

- v1.0.0 (Stable SPA release)
  - API freeze across `reactivity`, `vdom`, `router`, `forms`, `context`, `events`.
  - Documentation complete: getting started, concepts, API reference, guides (typing, testing, deployment, performance), and a full demo app.
  - Test suite: router/vdom/events/resources/forms; basic browser automation for Pyodide; CI passing.
  - (12) CLI scaffolding MVP (`wyb new`) shipped, marked experimental but supported.
  - Post-1.0 roadmap prepared (SSR story research, ecosystem integrations).

#### Notes and longer-term research

- SSR story (research): feasibility of server-rendered HTML with client handoff in Pyodide contexts.
- CLI scaffolding expansions: templates, generators, and plug-ins.

This roadmap should be reflected as GitHub milestones and issues. Each release should include a changelog entry in `docs/meta/changelog.md` and a PyPI release with pinned version.

#### Semantic Versioning (SemVer) policy

- Pre-1.0.0 (0.x.y)
  - Minor releases (0.MINOR) may include breaking changes.
  - Patch releases (0.MINOR.PATCH) are limited to backward-compatible fixes.
  - All breaking changes must be documented in the changelog.
- From 1.0.0 onwards
  - PATCH: backward-compatible bug fixes only.
  - MINOR: backward-compatible features and additions only.
  - MAJOR: any breaking change (API removals/renames, behavior changes, type/signature changes).
  - APIs may be explicitly marked “experimental” to exempt them from stability guarantees until stabilization.
- Alignment with this roadmap
  - Pre-1.0 allows API evolution and cleanup.
  - 1.0.0 introduces an API freeze; no breaking changes in minor or patch releases.

#### Release branching strategy (major versions)

- Maintenance branch
  - After `v1.0.0`, create a long-lived `1.x` (or `release/1.x`) branch.
  - Ship all `v1.y.z` releases from this branch (e.g., `v1.2.0`, `v1.3.0`).
- Next-major development
  - Option A: set `main` to v2 development after cutting `1.x`.
  - Option B: keep `main` on v1.x and develop v2 on a long-lived `next`/`v2` branch; merge into `main` when releasing `v2.0.0`.
- Parallel work
  - Target v1.x PRs to `1.x`; target v2 PRs to `main` (or `next`).
  - Forward-merge or cherry-pick from `1.x` → `main` regularly to carry fixes/improvements forward.
- Versioning and tags
  - Tag v1 releases on `1.x` (e.g., `v1.3.0`).
  - Tag v2 pre-releases/releases on `main`/`next` (e.g., `v2.0.0rc1`, `v2.0.0`).
- Breaking-change notation
  - Use Conventional Commits with `!` or a `BREAKING CHANGE:` footer and include migration notes.
- Patch policy
  - Keep one maintenance line per major (e.g., `1.x`) and apply patches only to the latest minor of that line (e.g., `1.5.x`); older minors are not patched.
