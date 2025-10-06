// Demo bootstrap: loads Pyodide, mounts the Wybthon library, then loads the demo app package and runs app.main().

const PYODIDE_VERSION = "0.25.1";
const PYODIDE_BASE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;

async function bootstrap() {
  try {
    const { loadPyodide } = await import(`${PYODIDE_BASE_URL}pyodide.mjs`);
    const pyodide = await loadPyodide({ indexURL: PYODIDE_BASE_URL });

    // Load the library modules from src into Pyodide's filesystem so `import wybthon` works.
    try { pyodide.FS.mkdir("/wybthon"); } catch {}
    const files = [
      "__init__.py",
      "dom.py",
      "component.py",
      "vdom.py",
      "reactivity.py",
      "events.py",
      "context.py",
      "router.py",
      "router_core.py",
      "forms.py",
      "dev.py",
    ];
    const cacheBust = Date.now();
    for (const f of files) {
      const resp = await fetch(`../../src/wybthon/${f}?v=${cacheBust}`);
      const txt = await resp.text();
      pyodide.FS.writeFile(`/wybthon/${f}`, new TextEncoder().encode(txt));
    }
    await pyodide.runPythonAsync("import sys; sys.path.insert(0, '/')");

    // Mount the demo app package under /app
    const ensureDir = (p) => { try { pyodide.FS.mkdir(p); } catch {} };
    ensureDir("/app");
    ensureDir("/app/components");
    ensureDir("/app/contexts");
    ensureDir("/app/about");
    ensureDir("/app/about/team");
    ensureDir("/app/docs");
    ensureDir("/app/fetch");
    ensureDir("/app/forms");
    ensureDir("/app/errors");

    const appFiles = [
      "app/__init__.py",
      "app/layout.py",
      "app/routes.py",
      "app/main.py",
      "app/page.py",
      "app/not_found.py",
      "app/components/__init__.py",
      "app/components/hello.py",
      "app/components/counter.py",
      "app/components/theme_label.py",
      "app/components/nav.py",
      "app/contexts/__init__.py",
      "app/contexts/theme.py",
      "app/about/__init__.py",
      "app/about/page.py",
      "app/about/team/__init__.py",
      "app/about/team/page.py",
      "app/docs/__init__.py",
      "app/docs/page.py",
      "app/fetch/__init__.py",
      "app/fetch/page.py",
      "app/forms/__init__.py",
      "app/forms/page.py",
      "app/errors/__init__.py",
      "app/errors/page.py",
    ];
    for (const f of appFiles) {
      const resp = await fetch(`./${f}?v=${cacheBust}`);
      const txt = await resp.text();
      pyodide.FS.writeFile(`/${f}`, new TextEncoder().encode(txt));
    }

    // Optional debug listings
    try {
      const listingLib = await pyodide.runPythonAsync("import os; os.listdir('/wybthon')");
      console.log("/wybthon contents:", listingLib);
      const listingApp = await pyodide.runPythonAsync("import os; os.listdir('/app')");
      console.log("/app contents:", listingApp);
    } catch {}

    // Import and run the app entrypoint
    await pyodide.runPythonAsync("from app.main import main; import asyncio; asyncio.get_event_loop();");
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

// HMR-lite: connect to dev server SSE for reloads
try {
  const es = new EventSource("/__sse");
  es.addEventListener("reload", () => {
    try { console.log("Reload event received; reloading page"); } catch {}
    location.reload();
  });
} catch {}
