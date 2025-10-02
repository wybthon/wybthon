### Contributing to Wybthon

Thanks for your interest in contributing. Wybthon is an experimental client-side Python framework (via Pyodide) for building interactive web apps with a Pythonic API. Contributions should keep the code simple, browser-friendly, and easy to understand.

## Quick start

Development uses Python ≥ 3.10.

```bash
# clone
git clone https://github.com/wybthon/wybthon.git
cd wybthon

# install package (editable) and dev tooling
pip install -e .
pip install -r requirements.txt   # currently: black

# format code
black src examples

# run the demo (from repo root) and open browser
python -m http.server
# then open http://localhost:8000/examples/demo/index.html
```

## Project layout (high-level)

- `src/wybthon/`
  - `component.py` – component model and base classes
  - `dom.py` – DOM interop and element helpers
  - `events.py` – DOM events and event utilities
  - `context.py` – context creation, providers, and consumption
  - `router.py` – client-side router, routes, links, navigation
  - `vdom.py` – virtual DOM nodes and renderer
  - `reactivity.py` – signals, effects, and batching
  - `__init__.py` – public exports
- `examples/`
  - `demo/` – minimal browser demo (`index.html`, `bootstrap.js`, `demo.py`, `child_component.html`)
- `README.md`, `pyproject.toml`, `requirements.txt`, `TODO.md`

## Coding guidelines

- **Style**: Black (see `requirements.txt`).
- **Naming**: prefer explicit, descriptive names; keep browser/runtime constraints in mind.
- **Structure**: separate pure logic from DOM interop; keep render/diff paths lean.
- **Examples**: keep examples minimal and reproducible; avoid large assets.
- **Tests**: if you add tests, place them under `tests/` and keep them fast (no network/large IO).

Common commands:

```bash
black src examples
python -m http.server
```

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
feat(reactivity): add computed() invalidation scheduling; stabilize batch() semantics
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
  - `component` – component model and base classes
  - `dom` – DOM interop and element helpers
  - `events` – DOM events and event utilities
  - `context` – context creation, providers, and consumption
  - `router` – routing, paths, and navigation helpers
  - `vdom` – virtual DOM and renderer
  - `reactivity` – signals, computed, effect, batching
  - `package` – `src/wybthon/__init__.py` exports and package boundary

- Other scopes:
  - `examples` – example(s) under `examples/`
  - `deps` – dependency updates and version pins (e.g., `requirements.txt`)
  - `mkdocs` – documentation site (MkDocs/Material) configuration and content under `docs/`
  - `pyproject` – `pyproject.toml` packaging/build metadata
  - `repo` – repository metadata and top-level files (e.g., `README.md`, `CONTRIBUTING.md`, `LICENSE`, `.gitignore`)
  - `tests` – unit/integration tests under `tests/` (if/when present)
  - `workflows` – CI pipelines under `.github/workflows/` (if/when present)

Note: Avoid redundant type==scope pairs (e.g., `docs(docs)`). Prefer a module scope (e.g., `docs(reactivity)`) or `docs(repo)` for top-level repository updates.

Examples:

```text
build(deps): refresh pinned tools
chore(pyproject): bump version to 0.0.2
docs(repo): expand README with demo instructions
docs(examples): clarify how to run the demo
feat(reactivity): introduce computed() with dependency tracking
feat(router): add Link component and navigate() helper
feat(context): introduce create_context/use_context with Provider
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
style: format code with Black
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
  - Example: `feat(reactivity): add computed()`
  - Imperative mood; no trailing period; aim for ≤ 72 chars; use `!` for breaking changes.
  - Prefer one primary scope; use comma-separated scopes only when necessary.
- **PR description**: include brief sections: What, Why, How (brief), Testing, Risks/Impact, Docs/Follow-ups.
  - Link issues with keywords (e.g., `Closes #123`).
- **Merging**: prefer “Squash and merge” with “Pull request title and description”.
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

- Format: `black src examples` passes.
- Tests: added/updated if applicable; all pass.
- Docs: update `README.md` and examples if behavior changes.
- Artifacts: none committed; demos load assets directly from the repo.

## Adding features or examples (quick recipes)

- Feature/API: implement under `src/wybthon/` in the appropriate module; update public exports in `src/wybthon/__init__.py`; add or update examples.
- Example: create a new folder under `examples/` with `index.html`, optional `bootstrap.js`, and Python script(s) loaded by Pyodide.

## Versioning and releases

- The version is tracked in `pyproject.toml` (`project.version`) and mirrored in `src/wybthon/__init__.py` as `__version__`. Use SemVer.
- Workflow (single `main` branch):
  - Contributors: branch off `main` and open PRs targeting `main`.
  - Maintainer (release): open a "Prepare release vX.Y.Z" PR from a short-lived branch → `main`, bump versions in both files, merge. (This can also be a single direct commit on `main`.)
  - Tag on `main`: `git tag -a vX.Y.Z -m "Release vX.Y.Z" && git push --tags`.
  - Automation: a GitHub Action publishes the package to PyPI when a `v*.*.*` tag is pushed (Trusted Publisher). For the first release, enable PyPI Trusted Publishing for this repo or do a one-time manual `twine upload dist/*`.
- Tag format: always prefix with `v` (e.g., `v0.1.0`).
- Release checklist:
  - Bump `pyproject.toml` and `src/wybthon/__init__.py` versions.
  - Build and verify: `python -m build && twine check dist/*`.
  - Create the annotated tag on `main` and push.
  - Draft the GitHub Release and include notes.

### Branching rules

- `main`: default branch.
- Feature branches: `feature/...` from `main`; hotfixes: `hotfix/...` from `main`.

#### Branch naming

- Use lowercase kebab-case; no spaces; keep names concise (aim ≤ 40 chars).
- Suggested prefixes (align with Conventional Commit categories):
  - `feature/<scope>-<short-desc>`
  - `fix/<issue-or-bug>-<short-desc>`
  - `chore/<short-desc>`
  - `docs/<short-desc>`
  - `ci/<short-desc>`
  - `refactor/<scope>-<short-desc>`
  - `test/<short-desc>`
  - `perf/<short-desc>`
  - `build/<short-desc>`
  - `release/vX.Y.Z`
  - `hotfix/<short-desc>`

Examples:

```text
feature/reactivity-computed
fix/vdom-keyed-order-123
docs/contributing-guidelines
ci/add-basic-workflow
build/update-black
refactor/component-state-split
test/component-lifecycle
release/v0.0.2
hotfix/dom-event-delegation
```

### CI

- If/when CI is added, PRs should run formatter/lint/tests and a build check.

## Security and provenance

- Do not commit secrets or credentials.
- Keep browser examples safe-by-default; avoid remote code execution patterns.

## License

By contributing, you agree that your contributions are licensed under the repository’s MIT License.
