// Demo bootstrap: loads Pyodide, mounts the Wybthon library, then loads the demo app package and runs app.main().

const PYODIDE_VERSION = "0.25.1";
const PYODIDE_BASE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;

// Minimal error overlay for Python exceptions (and JS errors) during development
let __wyb_overlay_el = null;
function showErrorOverlay(title, details) {
  try {
    if (__wyb_overlay_el) {
      __wyb_overlay_el.remove();
      __wyb_overlay_el = null;
    }
    const overlay = document.createElement('div');
    overlay.style.position = 'fixed';
    overlay.style.inset = '0';
    overlay.style.background = 'rgba(0,0,0,0.72)';
    overlay.style.backdropFilter = 'blur(2px)';
    overlay.style.zIndex = '2147483647';
    overlay.style.color = '#fff';
    overlay.style.overflow = 'auto';
    overlay.style.font = '13px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
    overlay.style.padding = '16px';

    const box = document.createElement('div');
    box.style.maxWidth = '960px';
    box.style.margin = '0 auto';
    box.style.background = '#1f2937';
    box.style.border = '1px solid #ef4444';
    box.style.borderRadius = '8px';
    box.style.boxShadow = '0 10px 25px rgba(0,0,0,0.35)';
    box.style.padding = '16px 20px';

    const hdr = document.createElement('div');
    hdr.style.display = 'flex';
    hdr.style.alignItems = 'center';
    hdr.style.justifyContent = 'space-between';
    const h = document.createElement('div');
    h.textContent = title || 'Error';
    h.style.fontWeight = '700';
    h.style.color = '#fca5a5';
    h.style.fontSize = '14px';
    hdr.appendChild(h);
    const btn = document.createElement('button');
    btn.textContent = 'Dismiss';
    btn.style.background = '#374151';
    btn.style.color = '#fff';
    btn.style.border = '1px solid #6b7280';
    btn.style.borderRadius = '6px';
    btn.style.padding = '6px 10px';
    btn.style.cursor = 'pointer';
    btn.onclick = () => { try { overlay.remove(); } catch {} };
    hdr.appendChild(btn);

    const pre = document.createElement('pre');
    pre.style.whiteSpace = 'pre-wrap';
    pre.style.marginTop = '12px';
    pre.textContent = details || '';

    box.appendChild(hdr);
    box.appendChild(pre);
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    __wyb_overlay_el = overlay;
  } catch {}
}

window.addEventListener('error', (e) => {
  try { showErrorOverlay('JavaScript Error', (e?.error && (e.error.stack || String(e.error))) || String(e.message)); } catch {}
});
window.addEventListener('unhandledrejection', (e) => {
  try { showErrorOverlay('Unhandled Promise Rejection', String(e?.reason?.stack || e?.reason || 'Unknown rejection')); } catch {}
});

async function bootstrap() {
  try {
    const { loadPyodide } = await import(`${PYODIDE_BASE_URL}pyodide.mjs`);
    const pyodide = await loadPyodide({ indexURL: PYODIDE_BASE_URL });

    // --- Helper: fetch a manifest from the dev server and load all .py files ---
    const cacheBust = Date.now();

    async function loadPyPackage(pyodide, manifestDir, fetchBase, mountRoot) {
      // Fetch the auto-generated file list from the dev server
      const resp = await fetch(`/__manifest?dir=${encodeURIComponent(manifestDir)}&v=${cacheBust}`);
      const files = await resp.json();  // e.g. ["__init__.py", "sub/page.py"]

      // Ensure all necessary directories exist in the Pyodide FS
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

      // Fetch each file and write it into Pyodide's virtual FS
      for (const f of files) {
        const url = `${fetchBase}/${f}?v=${cacheBust}`;
        const r = await fetch(url);
        const txt = await r.text();
        pyodide.FS.writeFile(`${mountRoot}/${f}`, new TextEncoder().encode(txt));
      }
      return files;
    }

    // Load the wybthon library package from src/
    const libFiles = await loadPyPackage(pyodide, "src/wybthon", "../../src/wybthon", "/wybthon");
    await pyodide.runPythonAsync("import sys; sys.path.insert(0, '/')");

    // Load the demo app package
    const appFiles = await loadPyPackage(pyodide, "examples/demo/app", "./app", "/app");

    console.log(`Loaded ${libFiles.length} library files, ${appFiles.length} app files`);

    // Import and run the app entrypoint
    try {
      await pyodide.runPythonAsync("from app.main import main; import asyncio; asyncio.get_event_loop();");
      await pyodide.runPythonAsync("await main()");
    } catch (err) {
      const msg = (err && (err.message || err.stack)) ? `${err.message || ''}\n${err.stack || ''}` : String(err);
      showErrorOverlay('Python Exception', msg);
      throw err;
    }
  } catch (err) {
    console.error("Failed to bootstrap Wybthon demo:", err);
    try {
      const msg = (err && (err.message || err.stack)) ? `${err.message || ''}\n${err.stack || ''}` : String(err);
      showErrorOverlay('Bootstrap Failure', msg);
    } catch {}
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
