"""Browser E2E suite package.

Making ``tests/e2e`` a package namespaces its ``conftest`` as ``e2e.conftest``
so it does not shadow the unit suite's top-level ``tests/conftest.py`` (which
unit modules import via ``from conftest import StubNode``). The fixture SPA
under ``app/`` is loaded inside Pyodide and is never imported by pytest.
"""
