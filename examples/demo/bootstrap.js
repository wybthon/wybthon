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
      "lazy.py",
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
    ensureDir("/app/patterns");

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
      "app/components/card.py",
      "app/components/names_list.py",
      "app/components/timer.py",
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
      "app/patterns/__init__.py",
      "app/patterns/page.py",
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
