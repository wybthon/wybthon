// E2E fixture bootstrap: loads Pyodide, mounts the Wybthon library from src/,
// then loads the fixture app package (tests/e2e/app) and runs app.main.main().
//
// This mirrors examples/demo/bootstrap.js but targets the dedicated E2E
// fixture app and records boot status on `window` so the Playwright harness
// can detect a failed boot deterministically (instead of timing out).

const PYODIDE_VERSION = "0.25.1";
const PYODIDE_BASE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;

window.__WYB_E2E_READY = false;
window.__WYB_E2E_ERROR = null;

function recordError(title, details) {
  const msg = `${title}: ${details || ""}`;
  try {
    window.__WYB_E2E_ERROR = msg;
    console.error(msg);
  } catch {}
}

window.addEventListener("error", (e) => {
  recordError("JavaScript Error", (e?.error && (e.error.stack || String(e.error))) || String(e.message));
});
window.addEventListener("unhandledrejection", (e) => {
  recordError("Unhandled Promise Rejection", String(e?.reason?.stack || e?.reason || "Unknown rejection"));
});

async function loadPyPackage(pyodide, manifestDir, fetchBase, mountRoot, cacheBust) {
  const resp = await fetch(`/__manifest?dir=${encodeURIComponent(manifestDir)}&v=${cacheBust}`);
  if (!resp.ok) {
    throw new Error(`Manifest fetch failed for ${manifestDir}: ${resp.status}`);
  }
  const files = await resp.json(); // e.g. ["__init__.py", "features/flow.py"]

  const dirs = new Set();
  dirs.add(mountRoot);
  for (const f of files) {
    const parts = f.split("/");
    for (let i = 1; i < parts.length; i++) {
      dirs.add(mountRoot + "/" + parts.slice(0, i).join("/"));
    }
  }
  for (const d of [...dirs].sort()) {
    try { pyodide.FS.mkdir(d); } catch {}
  }

  for (const f of files) {
    const url = `${fetchBase}/${f}?v=${cacheBust}`;
    const r = await fetch(url);
    if (!r.ok) {
      throw new Error(`Source fetch failed for ${url}: ${r.status}`);
    }
    const txt = await r.text();
    pyodide.FS.writeFile(`${mountRoot}/${f}`, new TextEncoder().encode(txt));
  }
  return files;
}

async function bootstrap() {
  try {
    const { loadPyodide } = await import(`${PYODIDE_BASE_URL}pyodide.mjs`);
    const pyodide = await loadPyodide({ indexURL: PYODIDE_BASE_URL });

    const cacheBust = Date.now();

    // Load the wybthon library package from src/ (../../ -> repo root).
    const libFiles = await loadPyPackage(pyodide, "src/wybthon", "../../src/wybthon", "/wybthon", cacheBust);
    await pyodide.runPythonAsync("import sys; sys.path.insert(0, '/')");

    // Load the E2E fixture app package (tests/e2e/app -> ./app).
    const appFiles = await loadPyPackage(pyodide, "tests/e2e/app", "./app", "/app", cacheBust);

    console.log(`E2E: loaded ${libFiles.length} library files, ${appFiles.length} app files`);

    await pyodide.runPythonAsync("from app.main import main; import asyncio; asyncio.get_event_loop();");
    await pyodide.runPythonAsync("await main()");
  } catch (err) {
    const msg = (err && (err.message || err.stack)) ? `${err.message || ""}\n${err.stack || ""}` : String(err);
    recordError("Bootstrap Failure", msg);
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootstrap);
} else {
  bootstrap();
}
