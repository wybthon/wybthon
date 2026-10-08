### Contributing to Wybthon

Thanks for your interest in contributing. Wybthon is "SolidJS for Python": a signals-first UI framework with a Pythonic API that runs in the browser on Pyodide. Contributions should keep the code simple, browser-friendly, and easy to understand.

## Quick start

Development uses Python 3.14, the same version as the Pyodide runtime that production builds target. CI runs the unit tests on Python 3.14 only.

Wybthon manages its environment and dependencies with [uv](https://docs.astral.sh/uv/). Install uv, then:

```bash
# clone
git clone https://github.com/wybthon/wybthon.git
cd wybthon

# create .venv and install the package (editable) with dev tooling
uv sync --group dev

# format code
uv run ruff format .

# run the unit tests
uv run pytest -q
```

`uv sync` creates `.venv` and installs everything from `pyproject.toml`, so there's no separate virtual environment step. Pass `--locked` to make it fail when `uv.lock` is stale, which is what CI does.

## Claiming an issue

To avoid duplicate work, claim an issue before you start on it:

1. Check the issue's assignee and any linked pull requests. If either exists, the issue is taken.
2. Comment on the issue to claim it and wait for a maintainer to assign it to you before opening a pull request.
3. If you stop working on an assigned issue, leave a comment so it can be reassigned.

Unsolicited pull requests for issues that are already assigned or already have an open pull request will be closed as duplicates, even if the work is good.

## Project layout (high-level)

- `src/wybthon/`
  - `reactivity/`: the reactive graph, split into `_core.py` (accessors, signals, computations, transitions, the scheduler), `_primitives.py` (`create_signal`, `create_memo`, effects, `create_reaction`, lifecycle, async helpers, `children`), `_actions.py` (`action`, `create_optimistic`, `affects`, `until`), `_list.py` (`map_array`, `repeat`), `_props.py` (`Props`, `ParentProps`, `Prop`, `prop`, `merge`, `omit`), and `_session.py` (hydration sessions and serialized server state)
  - `component.py`: the `@component` decorator and `Component`
  - `vnode.py`: virtual DOM nodes (`VNode`, `h`, `Fragment`, `hole`), item syntax, and t-string children
  - `html.py` / `svg.py`: element helpers built on `h()`
  - `_dom_props.py`: private; prop normalization and reactive attribute bindings (emits kernel commands)
  - `reconciler.py`: mounting, patching, and unmounting; `render`, `hydrate`, and `Root`
  - `_regions.py`: mounted list and branch regions (`For`, `Repeat`, `Show`, `Switch`)
  - `_template.py`: private; compiled shapes, generated mount functions, and native disposal
  - `kernel.py` / `_kernel.js`: the batched DOM command buffer and the JavaScript kernel it drives (including hydration claims), plus the `BrowserBackend` and `PythonBackend` backends
  - `server.py` / `_server_dom.py`: server rendering (`render_to_string`, `render_to_stream`) over an in-memory DOM
  - `request.py`: `RequestEvent`, `get_request_event`, `http_status`, and `http_header`
  - `dom.py`: `Element` and `Ref` (imperative DOM escape hatch)
  - `events.py`: root-scoped event delegation and the `DomEvent` payload object
  - `flow.py`: `Show`, `For`, `Repeat`, `Switch`/`Match`, `dynamic`, `client_only`, `NoHydration`, and `Hydration`
  - `loading.py`: `Loading` and `Reveal` boundaries
  - `error_boundary.py`: `Errored`
  - `store.py` / `_vector.py`: draft-first stores, projections, optimistic stores, `reconcile`, `snapshot`, `deep`, and the persistent vector behind staged store lists
  - `context.py`: `create_context` / `use_context` (the `Context` is its own provider)
  - `portal.py`, `lazy.py`: out-of-tree rendering and lazy-loaded components
  - `router.py`: client-side router, `RouteProps`, and the browser-agnostic matcher (`RouteSpec`, `resolve`)
  - `forms.py`: form state, validators, bindings, and a11y helpers
  - `virtual.py` / `scheduling.py`: list virtualization and cooperative scheduling
  - `testing.py`: `render`, `Screen` queries, `fire`, and `cleanup` for testing components in CPython
  - `diagnostics.py`: opt-in profiling counters and graph inspection
  - `_warnings.py`: dev-mode diagnostics and the dev mode flag
  - `dev.py`: the `wyb` command (`init`, `dev`, `build`, `preview`)
  - `build.py` / `_bootstrap.js` / `assets.py` / `_prerender.py`: production builds, the generated bootstrap, lazy chunks, and build-time prerendering
  - `__init__.py`: public exports (`__all__`)
- `tests/`
  - `conftest.py`: the `wyb` and `root_element` fixtures, which install a `kernel.PythonBackend` over an in-memory stub document and reload the DOM-facing modules per test; don't modify it casually
  - Unit tests (fast CPython, no browser): one module per area, such as `test_signals.py`, `test_component.py`, `test_props.py`, `test_flow.py`, `test_store.py`, `test_reconciler.py`, `test_ssr.py`, `test_router.py`, `test_forms.py`, and `test_testing.py`, plus contract suites (`test_*_contracts.py`)
  - `typing/`: type-checking fixtures (valid calls and expected errors) run by `test_typing_contracts.py`
  - `e2e/`: browser end-to-end suite (Playwright + Pyodide):
    - `wybthon.toml`, `index.html`, and `app/`: the fixture, an ordinary Wybthon project with one route per framework feature (`app/features/*.py`) and `data-testid` hooks, served by `wyb dev --dir tests/e2e`
    - `test_*.py`: per-feature Playwright tests; `conftest.py` boots Pyodide once and isolates tests through a `/blank` route
    - `test_pyodide_smoke.py`: fixture boot smoke test
- `docs/`: MkDocs Material site (`mkdocs.yml` at the root); API pages render docstrings through mkdocstrings
- `docs/rfcs/`: design documents for large changes; see [RFCs](docs/rfcs/index.md)
- `benchmarks/`: native and browser benchmarks, plus the `check_work.py` command-count gates
- `README.md`, `pyproject.toml`, `uv.lock`, `CHANGELOG.md` (generated by semantic-release; don't edit by hand)

## Coding guidelines

- **Style**: Ruff formats (`uv run ruff format .`) and lints (`uv run ruff check .`); it ships in the `dev` dependency group.
- **Naming**: prefer explicit, descriptive names; keep browser/runtime constraints in mind.
- **Structure**: separate pure logic from DOM interop; keep render/diff paths lean.
- **Examples**: keep docs examples minimal and reproducible; larger demo apps live in standalone repos under the [wybthon organization](https://github.com/wybthon).
- **Tests**: put fast CPython unit tests directly under `tests/` (browser APIs are stubbed, no network/large IO). Browser-dependent behaviour goes in the Playwright + Pyodide suite under `tests/e2e/`; mark those with the `e2e` pytest marker so they stay out of the fast unit run. See the [Testing guide](docs/guides/testing.md).
- **Docstrings**: Google-style for all public modules, classes, and functions. See the
  [Documentation style guide](docs/meta/style-guide.md) for the full conventions, or
  the rendered version at <https://wybthon.com/meta/style-guide/>.
- **Comments**: explain *why*, not *what*. Delete redundant comments during refactors.

Common commands:

```bash
uv run ruff format .
uv run ruff check .
uv run mypy
uv run pytest -q                     # unit tests (the e2e suite is excluded by default)
uv run pytest -q -m e2e tests/e2e    # browser tests (Playwright + Pyodide)
./scripts/check.sh                   # everything ci.yml's unit job runs, in order
```

To try a change in a real app, create a scratch project with `uv run wyb init /tmp/scratch` and run `uv run wyb dev --dir /tmp/scratch --open`. The dev server only serves projects with a `wybthon.toml`.

## Conventional Commits

This project uses Conventional Commits. Use the form:

```
<type>(<scope>): <subject>

[optional body]

[optional footer(s)]
```

### Commit message character set

- **Encoding**: UTF‑8 is allowed and preferred across subjects and bodies.
- **Subjects** may include UTF‑8 symbols when they add clarity; keep the subject ≤ 72 chars and avoid emoji.
- For maximum legacy compatibility, prefer ASCII in the subject and use UTF‑8 in the body.

Example (UTF‑8 subject):

```
feat(reactivity): add async memo scheduling; stabilize flush() semantics
```

Accepted types (stick to the standard):

- `build` – build system or external dependencies (e.g., requirements, packaging)
- `chore` – maintenance (no user-visible behavior change)
- `ci` – continuous integration configuration
- `docs` – documentation only
- `feat` – user-facing feature or capability
- `fix` – bug fix
- `perf` – performance improvements
- `refactor` – code change that neither fixes a bug nor adds a feature
- `revert` – revert of a previous commit
- `style` – formatting/whitespace (no code behavior)
- `test` – add/adjust tests only

Recommended scopes (choose the smallest, most accurate unit; prefer module/directory names):

- Module/directory scopes:
  - `component` – the `@component` decorator and prop binding
  - `context` – `create_context`, the callable `Context`, and `use_context`
  - `build` – production builds, the bootstrap, lazy chunks, and prerendering
  - `dev` – the `wyb` command, dev server, and live reload (SSE)
  - `dom` – `Element` and `Ref`
  - `error_boundary` – `Errored` and fallback rendering
  - `events` – delegated DOM events and `DomEvent`
  - `flow` – control-flow components (`Show`, `For`, `Repeat`, `Switch`, `Match`, `dynamic`, `client_only`)
  - `forms` – form state, validators, bindings, and a11y helpers
  - `html` – HTML element helpers and `element()`
  - `kernel` – batched DOM command buffer, JS kernel, and rendering backends
  - `lazy` – lazy loading and preloading utilities
  - `loading` – `Loading` and `Reveal` boundaries
  - `package` – `src/wybthon/__init__.py` exports and package boundary
  - `portal` – portal rendering to out-of-tree DOM containers
  - `props` – `Props`, `Prop`, `prop`, `merge`, `omit`, and DOM prop application (`_dom_props`)
  - `reactivity` – the reactive graph and primitives (`create_signal`, `create_memo`, `create_effect`, actions, `Props`)
  - `reconciler` – mounting, patching, and unmounting; `render` and `Root`
  - `router` – routing, `Link`, and navigation helpers
  - `server` – server rendering, streaming, and the request event (`wybthon.server`, `request`)
  - `store` – reactive stores (`create_store`, `create_projection`, `reconcile`) for nested state
  - `svg` – SVG element helpers
  - `testing` – `wybthon.testing` (render, queries, `fire`)
  - `template` – compiled shapes and generated mount functions (`_template`)
  - `vdom` – changes that span `vnode`, `reconciler`, and `_dom_props` together
  - `vnode` – `VNode`, `h`, `Fragment`, and `hole`
  - `warnings` – development mode warnings and error reporting

- Other scopes:
  - `deps` – dependency updates and version pins (e.g., `pyproject.toml`, `uv.lock`)
  - `mkdocs` – documentation site (MkDocs/Material) configuration and content under `docs/`
  - `pyproject` – `pyproject.toml` packaging/build metadata
  - `repo` – repository metadata and top-level files (e.g., `README.md`, `CONTRIBUTING.md`, `LICENSE`, `.gitignore`)
  - `bench` – benchmarks and performance scripts under `benchmarks/`
  - `tests` – unit/integration tests under `tests/` (if/when present)
  - `workflows` – CI pipelines under `.github/workflows/` (if/when present)

Note: Avoid redundant type==scope pairs (e.g., `docs(docs)`). Prefer a module scope (e.g., `docs(reactivity)`) or `docs(repo)` for top-level repository updates.

Examples:

```text
build(deps): refresh pinned tools
chore(pyproject): bump version to 0.0.2
docs(repo): expand README with setup instructions
feat(reactivity): introduce create_memo() with dependency tracking
feat(router): add Link component and navigate() helper
feat(context): introduce create_context/use_context
fix(vdom): correct keyed children diff order
perf(dom): reduce attribute writes during render
refactor(component): split props/state handling helpers
revert(vdom): revert refactor causing regression in event delegation
test(component): add basic component lifecycle tests
test(router): add route matching tests
test(events): cover DomEvent normalization
```

Examples (no scope):

```text
build: update packaging metadata
chore: update .gitignore patterns
docs: add contributing guidelines
revert: revert "refactor(component): split props/state handling helpers"
style: format code with Ruff
```

Breaking changes:

- Use `!` after the type/scope or a `BREAKING CHANGE:` footer.

```text
feat(vdom)!: change render() to return mount handle

BREAKING CHANGE: render() now returns a handle for unmount; update examples.
```

### Multiple scopes (optional)

- Comma-separate scopes without spaces: `type(scope1,scope2): ...`
- Prefer a single scope when possible; use multiple only when the change genuinely spans tightly related areas.

Scope ordering (house style):

- Put the most impacted scope first (e.g., `repo`), then any secondary scopes.
- For extra consistency, alphabetize the remaining scopes after the primary.
- Keep it to 1–3 scopes max.

Example:

```text
feat(vdom,component): expose keyed fragments; adapt component mount flow
```

## Pull requests and squash merges

- **PR title**: use Conventional Commit format.
  - Example: `feat(reactivity): add create_reaction()`
  - Imperative mood; no trailing period; aim for ≤ 72 chars; use `!` for breaking changes.
  - Prefer one primary scope; use comma-separated scopes only when necessary.
- **PR description**: include brief sections: What, Why, How (brief), Testing, Risks/Impact, Docs/Follow-ups.
  - Link issues with keywords (e.g., `Closes #123`).
- **Merging**: prefer "Squash and merge" with "Pull request title and description".
- Keep PRs focused; avoid unrelated changes in the same PR.

Conventional Commits applies to the subject line (your PR title) and optional footers. The PR body is free-form; when squashing, it becomes the commit body. Place any footers at the bottom of the description.

Recommended PR template:

```text
What
- Short summary of the change

Why
- Motivation/user value

How (brief)
- Key implementation notes or decisions

Testing
- Local/CI coverage; links to tests if relevant

Risks/Impact
- Compat, rollout, perf, security; mitigations

Docs/Follow-ups
- Docs updated or TODO next steps

Closes #123
BREAKING CHANGE: <details if any>
Co-authored-by: Name <email>
```

## Pull request checklist

- PR title: Conventional Commits format (CI-enforced by `pr-lint.yml`).
- Format and lint: `uv run ruff format --check .` and `uv run ruff check .` pass.
- Types: `uv run mypy` passes.
- Tests: added/updated if applicable; all pass.
- Docs: update `README.md` and the docs site if behavior changes.
- Artifacts: none committed.

## Large changes and RFCs

Write an RFC before starting a change that alters public API, a runtime contract, the kernel wire protocol, or the build output, or that adds a subsystem. Copy [`docs/rfcs/0000-template.md`](docs/rfcs/0000-template.md), open a pull request with the draft, and follow the process in [`docs/rfcs/index.md`](docs/rfcs/index.md). The pull request that completes an RFC's implementation also sets its status to `Implemented`.

## Adding features (quick recipe)

- Feature/API: implement under `src/wybthon/` in the appropriate module; update public exports in `src/wybthon/__init__.py`; add or update docs and tests. Showcase apps belong in standalone repos under the [wybthon organization](https://github.com/wybthon).

## Versioning and releases

- The version is tracked in `pyproject.toml` (`project.version`) and mirrored in `src/wybthon/__init__.py` as `__version__`. Both files are updated automatically by [python-semantic-release](https://python-semantic-release.readthedocs.io/).
- **Automated release pipeline** (on every merge to `main`):
  1. `python-semantic-release` scans Conventional Commit messages since the last tag.
  2. It determines the next SemVer bump: `feat` → **minor**, `fix`/`perf` → **patch**, `BREAKING CHANGE` → **major** (minor while version < 1.0).
  3. Version files are updated, `CHANGELOG.md` is generated, and a tagged release commit (`chore(release): vX.Y.Z`) is pushed.
  4. A GitHub Release is created with auto-generated release notes and the built sdist/wheel attached.
  5. When drafts are disabled, the package is also published to PyPI via Trusted Publishing.
- **Draft / published toggle**: the `DRAFT_RELEASE` variable at the top of `.github/workflows/release.yml` controls release mode. Set to `"true"` (the default) for draft GitHub Releases with PyPI publishing skipped; flip to `"false"` to publish releases and upload to PyPI immediately.
- Commit types that trigger a release: `feat` (minor), `fix` and `perf` (patch), `BREAKING CHANGE` (major). All other types (`build`, `chore`, `ci`, `docs`, `refactor`, `revert`, `style`, `test`) are recorded in the changelog but do **not** trigger a release on their own.
- Tag format: `v`-prefixed (e.g., `v0.9.0`).
- Manual version bumps are no longer needed; just merge PRs with valid Conventional Commit titles. For ad-hoc runs, use the workflow's **Run workflow** button (`workflow_dispatch`).

### Branching rules

- `main`: default branch.
- All work branches are created from `main`.

#### Branch naming

- Use lowercase kebab-case; no spaces; keep names concise (aim ≤ 40 chars).
- Branch prefixes match Conventional Commit types:
  - `feat/<scope>-<short-desc>`
  - `fix/<issue-or-bug>-<short-desc>`
  - `chore/<short-desc>`
  - `docs/<short-desc>`
  - `ci/<short-desc>`
  - `refactor/<scope>-<short-desc>`
  - `test/<short-desc>`
  - `perf/<short-desc>`
  - `build/<short-desc>`

Examples:

```text
feat/reactivity-reaction
fix/vdom-keyed-order-123
docs/contributing-guidelines
ci/add-basic-workflow
build/update-ruff
refactor/component-state-split
test/component-lifecycle
fix/dom-event-delegation
```

### CI

- **CI** (`ci.yml`): runs the Ruff format check, the Ruff linter, mypy, and the unit tests with an 80% coverage gate (the `build` job, on Python 3.14) on every push and PR. A separate `e2e` job runs the full browser suite under `tests/e2e/` (fixture project plus boot smoke test) in headless Chromium with Pyodide, caching the Playwright browser between runs.
- **PR Lint** (`pr-lint.yml`): validates the PR title against Conventional Commits format (protects squash merges) and checks individual commit messages via commitlint (protects rebase merges). Recommended: add the **PR title** job as a required status check in branch-protection settings.
- **Release** (`release.yml`): runs on merge to `main`; computes version, generates changelog, tags, creates GitHub Release, and (when `DRAFT_RELEASE` is `"false"`) publishes to PyPI.
- **Docs** (`docs.yml`): builds the MkDocs site with `--strict` (fail on warning) on every push and PR; on push to `main` it also deploys to GitHub Pages.

## Security and provenance

- Don't commit secrets or credentials.
- Keep browser examples safe-by-default; avoid remote code execution patterns.

## License

By contributing, you agree that your contributions are licensed under the repository's MIT License.
