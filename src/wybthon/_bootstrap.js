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
    const runtime = import(runtimeURL + "pyodide.mjs").then(({ loadPyodide }) =>
      loadPyodide({ indexURL: runtimeURL, packages: config.packages })
    ).then(value => {
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
    await pyodide.runPythonAsync("import sys; sys.path.insert(0, '/wybthon-app')");
    if (config.wheels.length) {
      await pyodide.loadPackage("micropip");
      pyodide.globals.set("_wyb_requirements", JSON.stringify(config.wheels));
      await pyodide.runPythonAsync("import micropip, json; await micropip.install(json.loads(_wyb_requirements)); del _wyb_requirements");
    }
    // Production bundles turn dev mode off before the application imports.
    await pyodide.runPythonAsync(`import wybthon; wybthon.set_dev_mode(${config.dev ? "True" : "False"})`);
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
