# Contributing

Welcome! This page is a quick orientation for contributors. The full and authoritative guidelines live in the repository's [`CONTRIBUTING.md`](https://github.com/wybthon/wybthon/blob/main/CONTRIBUTING.md); please skim it before opening a pull request.

## Quick start

```bash
git clone https://github.com/wybthon/wybthon.git
cd wybthon
pip install -e .
```

Everything you need to develop the framework, the docs site, and the demo app is now installed. Run the demo with `wyb dev --dir .` and open the URL it prints.

## Where to make changes

| Want to change... | Look here |
| --- | --- |
| Framework code | [`src/wybthon/`](https://github.com/wybthon/wybthon/tree/main/src/wybthon) |
| Demo app | [`examples/demo/`](https://github.com/wybthon/wybthon/tree/main/examples/demo) |
| Documentation site | [`docs/`](https://github.com/wybthon/wybthon/tree/main/docs) |
| Tests | [`tests/`](https://github.com/wybthon/wybthon/tree/main/tests) |
| Lint / format / typing config | [`pyproject.toml`](https://github.com/wybthon/wybthon/blob/main/pyproject.toml) |

## Coding standards

- Source code targets **Python 3.10+** with type hints throughout.
- Docstrings use the **Google style** documented in the [docs style guide](style-guide.md). The Ruff `pydocstyle` ruleset enforces this.
- Run `ruff check .` and `ruff format --check .` before pushing.
- Run `mypy src` and `pytest` to verify types and tests.

## Updating documentation

- Author new pages under `docs/` and add them to `mkdocs.yml`.
- Build the site locally with `mkdocs serve` (or `mkdocs build --strict` to fail on warnings the way CI does).
- Cross-reference Python symbols with `[label][wybthon.symbol]` syntax; see the [style guide](style-guide.md) for details.

## Filing a pull request

1. Open an issue first for non-trivial changes so we can align on the approach.
2. Keep PRs focused: one logical change per PR makes review easier.
3. Add or update tests when changing behavior.
4. Update the relevant docs page(s) so the framework stays self-explanatory.

## Next steps

- Skim the [docs style guide](style-guide.md) before writing prose.
- Browse open issues at [`github.com/wybthon/wybthon/issues`](https://github.com/wybthon/wybthon/issues) for ways to help.
