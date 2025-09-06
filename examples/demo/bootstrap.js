// Demo bootstrap: loads Pyodide and runs the demo app using the packaged library API.

const PYODIDE_VERSION = "0.25.1";
const PYODIDE_BASE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;

async function bootstrap() {
  try {
    const { loadPyodide } = await import(`${PYODIDE_BASE_URL}pyodide.mjs`);
    const pyodide = await loadPyodide({ indexURL: PYODIDE_BASE_URL });

    // Load the library modules from src into Pyodide's filesystem so `import wybthon` works.
    try { pyodide.FS.mkdir("/wybthon"); } catch {}
    const files = ["__init__.py", "dom.py", "component.py", "vdom.py", "reactivity.py", "events.py", "context.py", "router.py"];
    const cacheBust = Date.now();
    for (const f of files) {
      const resp = await fetch(`../../src/wybthon/${f}?v=${cacheBust}`);
      const txt = await resp.text();
      pyodide.FS.writeFile(`/wybthon/${f}`, new TextEncoder().encode(txt));
    }
    await pyodide.runPythonAsync("import sys; sys.path.insert(0, '/')");

    // Debug: list files to ensure events.py is present
    try {
      const listing = await pyodide.runPythonAsync("import os; os.listdir('/wybthon')");
      console.log("/wybthon contents:", listing);
    } catch {}

    // Load the demo Python module from examples (contains the example components + main)
    const response = await fetch("./demo.py");
    const code = await response.text();
    pyodide.runPython(code);

    await pyodide.runPythonAsync("await main()");
  } catch (err) {
    console.error("Failed to bootstrap Wybthon demo:", err);
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootstrap);
} else {
  bootstrap();
}
