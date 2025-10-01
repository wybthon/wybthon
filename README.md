# Wybthon

**Wybthon** is an experimental client-side web framework written in Python, inspired by popular JavaScript frameworks like React and Angular. The goal is to provide a Pythonic approach to building interactive web applications.

## Installation

```sh
pip install wybthon
```

### Use in Pyodide (micropip)

```python
import micropip
await micropip.install("wybthon")

import wybthon as wy
```

## Project Structure

```plaintext
.
├── README.md
├── LICENSE
├── pyproject.toml
├── requirements.txt
├── src/
│   └── wybthon/
│       ├── __init__.py
│       ├── component.py
│       ├── context.py
│       ├── dev.py
│       ├── dom.py
│       ├── events.py
│       ├── forms.py
│       ├── reactivity.py
│       ├── router.py
│       └── vdom.py
├── docs/
│   ├── index.md
│   ├── getting-started.md
│   ├── api.md
│   └── examples.md
├── examples/
│   └── demo/
│       ├── index.html
│       ├── bootstrap.js
│       ├── demo.py
│       └── child_component.html
└── tests/
    ├── test_context.py
    ├── test_dev.py
    ├── test_forms.py
    ├── test_reactivity.py
    └── test_validators.py
```

- **src/wybthon/**: Core library package modules.
- **docs/**: Documentation sources for MkDocs.
- **examples/**: Demo running in the browser via Pyodide.
- **tests/**: Unit tests.

## Getting Started

To run the example application:

1. **Clone the repository**:
    ```sh
    git clone https://github.com/wybthon/wybthon.git
    cd wybthon
    ```

2. **Start a simple web server** from the repo root:
    ```sh
    python -m http.server
    ```

3. **Open your browser** to `http://localhost:8000/examples/demo/index.html`.
