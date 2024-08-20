# Wybthon

**Wybthon** is an experimental client-side web framework written in Python, inspired by popular JavaScript frameworks like React and Angular. The goal is to provide a Pythonic approach to building interactive web applications.

## Project Structure

```plaintext
.
├── README.md
├── apps
├── libs
│   └── wybthon
│       ├── index.html
│       ├── start_web_server.sh
│       └── wybthon.py
└── requirements.txt
```

- **apps/**: Directory for future web applications built with Wybthon.
- **libs/wybthon/**: Core library files for Wybthon.
    - `index.html`: Example HTML file that loads the Wybthon framework using Pyodide.
    - `start_web_server.sh`: Script to start a simple web server for development.
    - `wybthon.py`: Initial implementation of Wybthon, including base classes and a simple component example.
- **requirements.txt**: Placeholder for future dependencies.

## Getting Started

To run the example application:

1. **Clone the repository**:
    ```sh
    git clone https://github.com/owenthcarey/wybthon.git
    cd wybthon
    ```

2. **Start the development server**:
    ```sh
    sh libs/wybthon/start_web_server.sh
    ```

3. **Open your browser** and navigate to `http://localhost:8000` to see the "Hello, world!" message rendered by the `AppComponent`.

## Future Plans

- Add composability and state management.
- Create a component lifecycle similar to other frameworks.
- Publish Wybthon as a PIP package.
- Expand the project to support more complex web applications.

