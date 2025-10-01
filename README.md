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
├── pyproject.toml
├── src/
│   └── wybthon/
│       └── __init__.py
└── examples/
    └── demo/
        ├── index.html
        ├── bootstrap.js
        ├── demo.py
        └── child_component.html
```

- **src/wybthon/**: Core library package.
- **examples/**: Demo running in the browser via Pyodide.

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

## Future Plans

- Add composability and state management.
- Create a component lifecycle similar to other frameworks.
- Publish Wybthon as a PIP package.
- Expand the project to support more complex web applications.
