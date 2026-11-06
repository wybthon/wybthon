// Generated production bundles use this loader, with a pinned Pyodide runtime.
const manifestURL = new URL("../manifest.json", import.meta.url);
const state = globalThis.__WYB = { status: "loading", error: null, timings: {}, pyodide: null };
const started = performance.now();
const chunks = new Map();

// Record input on server-rendered content until Python has hydrated it;
// the kernel replays the queue through delegated handlers afterwards.
const captured = globalThis.__wybQueue = [];
const captureTypes = ["click", "input", "change", "submit", "keydown"];
function capture(event) {
  if (globalThis.__wybQueue !== captured) return;
  const target = event.target;
  if (!(target instanceof Node)) return;
  captured.push({
    event,
    value: "value" in target ? target.value : undefined,
    checked: "checked" in target ? target.checked : undefined,
  });
  // A form submitted before hydration would navigate away from the app.
  const root = document.querySelector("[data-wyb-root]");
  if (event.type === "submit" && (root === null || root.contains(target))) event.preventDefault();
}
for (const type of captureTypes) document.addEventListener(type, capture, true);
function stopCapturing() {
  for (const type of captureTypes) document.removeEventListener(type, capture, true);
  if (globalThis.__wybQueue === captured) globalThis.__wybQueue = null;
}

// A memory snapshot of a Pyodide runtime that has already imported Wybthon
// (RFC 0006). The first visit boots normally, then builds one in a worker
// when the page is idle; later visits (and every `wyb dev` reload) restore
// it instead of booting Python and importing the framework again.
// Each app keeps its snapshots in a cache of its own, named by its base
// path, so apps sharing an origin don't evict each other's.
function snapshotCache(config) {
  return `wybthon-snapshot ${config.base || "/"}`;
}

function snapshotRequest(config) {
  return new URL(`${config.base || "/"}__wyb_snapshot/${config.snapshot}`, location.href).href;
}

async function readSnapshot(config) {
  if (!config.snapshot || typeof caches === "undefined") return null;
  try {
    const cache = await caches.open(snapshotCache(config));
    const response = await cache.match(snapshotRequest(config));
    return response ? new Uint8Array(await response.arrayBuffer()) : null;
  } catch (_) {
    return null;
  }
}

async function forgetSnapshot(config) {
  try {
    const cache = await caches.open(snapshotCache(config));
    await cache.delete(snapshotRequest(config));
  } catch (_) {}
}

// A build that failed (storage full, a private window that can't keep it)
// isn't retried for a week, so a browser that can't store snapshots doesn't
// pay for building one on every visit.
const snapshotRetryMs = 7 * 24 * 60 * 60 * 1000;

function snapshotFailureKey(config) {
  return `wybthon-snapshot-failed ${config.base || "/"}`;
}

function snapshotFailedRecently(config) {
  try {
    const failed = JSON.parse(localStorage.getItem(snapshotFailureKey(config)) || "null");
    return failed !== null && failed.key === config.snapshot && Date.now() - failed.at < snapshotRetryMs;
  } catch (_) {
    return false;
  }
}

function recordSnapshotFailure(config) {
  try {
    localStorage.setItem(snapshotFailureKey(config), JSON.stringify({ key: config.snapshot, at: Date.now() }));
  } catch (_) {}
}

// The worker that builds a snapshot: a fresh runtime that imports the
// framework and nothing else (application modules may touch the page when
// they're imported, which a snapshot can't hold).
const snapshotWorker = `
self.onmessage = async (event) => {
  const { indexURL, runtimeURL, request, cacheName } = event.data;
  try {
    const started = performance.now();
    const { loadPyodide } = await import(indexURL + "pyodide.mjs");
    const pyodide = await loadPyodide({ indexURL, _makeSnapshot: true });
    const response = await fetch(runtimeURL);
    if (!response.ok) throw new Error("runtime archive: " + response.status);
    pyodide.unpackArchive(new Uint8Array(await response.arrayBuffer()), "zip", { extractDir: "/wybthon-app" });
    pyodide.runPython("import sys\\nif '/wybthon-app' not in sys.path: sys.path.insert(0, '/wybthon-app')\\nimport wybthon._snapshot\\nwybthon._snapshot.preload()");
    const snapshot = pyodide.makeMemorySnapshot();
    const cache = await caches.open(cacheName);
    for (const old of await cache.keys()) await cache.delete(old);
    await cache.put(request, new Response(snapshot, { headers: { "content-type": "application/octet-stream" } }));
    self.postMessage({ ok: true, bytes: snapshot.byteLength, ms: performance.now() - started });
  } catch (error) {
    self.postMessage({ ok: false, error: String(error && error.stack || error) });
  }
};
`;

function buildSnapshot(config, runtimeURL) {
  if (typeof Worker === "undefined" || typeof caches === "undefined" || snapshotFailedRecently(config)) return;
  const start = () => {
    let worker;
    const url = URL.createObjectURL(new Blob([snapshotWorker], { type: "text/javascript" }));
    try {
      worker = new Worker(url, { type: "module" });
    } catch (_) {
      URL.revokeObjectURL(url);
      return;
    }
    const finish = (result) => {
      if (result.error) recordSnapshotFailure(config);
      state.snapshot = result;
      worker.terminate();
      URL.revokeObjectURL(url);
      globalThis.dispatchEvent(new CustomEvent("wybthon:snapshot", { detail: result }));
    };
    worker.onerror = (event) => finish({ error: String(event.message || "the snapshot worker failed to start") });
    worker.onmessage = (event) =>
      finish(event.data.ok ? { built: true, bytes: event.data.bytes, ms: event.data.ms } : { error: event.data.error });
    worker.postMessage({
      indexURL: runtimeURL,
      runtimeURL: new URL(config.runtime, manifestURL).href,
      request: snapshotRequest(config),
      cacheName: snapshotCache(config),
    });
  };
  if (typeof requestIdleCallback === "function") requestIdleCallback(start, { timeout: 5000 });
  else setTimeout(start, 1000);
}

async function fetchBytes(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Failed to fetch ${url}: ${response.status}`);
  return new Uint8Array(await response.arrayBuffer());
}

state.ready = (async () => {
  try {
    // `wyb build` inlines the manifest into the page; fetch it only when absent.
    const inline = document.getElementById("wyb-manifest");
    let config;
    if (inline !== null) {
      config = JSON.parse(inline.textContent);
    } else {
      const response = await fetch(manifestURL, { cache: "no-cache" });
      if (!response.ok) throw new Error(`Manifest request failed: ${response.status}`);
      config = await response.json();
    }
    const mount = document.querySelector(config.mount || "#app");
    if (mount === null) throw new Error(`Mount element not found: ${config.mount}`);
    mount.setAttribute("data-wyb-root", "");
    const hydrating = !!mount.querySelector(":scope > script[data-wyb-state]");
    state.hydrated = hydrating;
    const runtimeURL = new URL(config.pyodide_url, manifestURL).href;
    const runtimeStart = performance.now();
    const snapshot = readSnapshot(config);
    const runtime = Promise.all([import(runtimeURL + "pyodide.mjs"), snapshot]).then(async ([{ loadPyodide }, saved]) => {
      if (saved !== null) {
        try {
          const restored = await loadPyodide({ indexURL: runtimeURL, _loadSnapshot: saved });
          state.timings.snapshot = true;
          return restored;
        } catch (error) {
          // A snapshot this runtime can't restore: drop it and boot normally.
          console.warn("Wybthon: discarding a snapshot that couldn't be restored", error);
          await forgetSnapshot(config);
        }
      }
      state.timings.snapshot = false;
      return loadPyodide({ indexURL: runtimeURL, packages: config.packages });
    }).then(value => {
      state.timings.pyodide_ms = performance.now() - runtimeStart;
      return value;
    });
    const archiveStart = performance.now();
    const archives = Promise.all([config.runtime, config.application].map(path => fetchBytes(new URL(path, manifestURL))))
      .then(value => {
        state.timings.archives_ms = performance.now() - archiveStart;
        return value;
      });
    const [pyodide, bundles] = await Promise.all([runtime, archives]);
    state.pyodide = pyodide;
    const unpackStart = performance.now();
    for (const bytes of bundles) pyodide.unpackArchive(bytes, "zip", { extractDir: "/wybthon-app" });
    state.timings.unpack_ms = performance.now() - unpackStart;
    state.loadChunk = async (name) => {
      if (!Object.hasOwn(config.chunks, name)) throw new Error(`Unknown Wybthon chunk: ${name}`);
      if (!chunks.has(name)) {
        const promise = fetchBytes(new URL(config.chunks[name], manifestURL)).then(bytes => {
          pyodide.unpackArchive(bytes, "zip", { extractDir: "/wybthon-app" });
        }).catch(error => { chunks.delete(name); throw error; });
        chunks.set(name, promise);
      }
      await chunks.get(name);
    };
    const appStart = performance.now();
    await pyodide.runPythonAsync("import sys\nif '/wybthon-app' not in sys.path: sys.path.insert(0, '/wybthon-app')");
    if (config.wheels.length) {
      await pyodide.loadPackage("micropip");
      pyodide.globals.set("_wyb_requirements", JSON.stringify(config.wheels));
      await pyodide.runPythonAsync("import micropip, json; await micropip.install(json.loads(_wyb_requirements)); del _wyb_requirements");
    }
    // Production bundles turn dev mode off before the application imports.
    await pyodide.runPythonAsync(`import wybthon; wybthon.set_dev_mode(${config.dev ? "True" : "False"})`);
    // `wyb dev` replaces changed modules in place; it records mounted
    // components from the start so it can remount them (RFC 0006).
    if (globalThis.__wybHot) await pyodide.runPythonAsync("import wybthon._hmr; wybthon._hmr.enable()");
    pyodide.globals.set("_wyb_entry", config.entry);
    pyodide.globals.set("_wyb_mount", config.mount || "#app");
    pyodide.globals.set("_wyb_hydrate", hydrating);
    await pyodide.runPythonAsync(`
import importlib, inspect
_wyb_module, _wyb_export = _wyb_entry.split(':', 1)
_wyb_view = getattr(importlib.import_module(_wyb_module), _wyb_export)()
if inspect.isawaitable(_wyb_view):
    _wyb_view = await _wyb_view
if _wyb_view is None:
    raise TypeError(f"{_wyb_entry} must return the root view (for example App()), not render it")
from wybthon import flush, hydrate, render
(hydrate if _wyb_hydrate else render)(_wyb_view, _wyb_mount)
flush()
del _wyb_entry, _wyb_mount, _wyb_hydrate, _wyb_module, _wyb_export, _wyb_view
`);
    stopCapturing();
    state.timings.application_ms = performance.now() - appStart;
    document.getElementById("wyb-loading")?.remove();
    state.status = "ready";
    state.timings.ready_ms = performance.now() - started;
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    state.timings.ready_frame_ms = performance.now() - started;
    globalThis.dispatchEvent(new CustomEvent("wybthon:ready", { detail: state.timings }));
    if (config.snapshot && !state.timings.snapshot) buildSnapshot(config, runtimeURL);
    return state;
  } catch (error) {
    stopCapturing();
    state.status = "error";
    state.error = String(error?.stack || error);
    const message = document.getElementById("wyb-loading");
    if (message) message.textContent = "The application couldn't start.";
    console.error(error);
    return state;
  }
})();
