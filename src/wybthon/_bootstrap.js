// Generated production bundles use this loader, with a pinned Pyodide runtime.
const manifestURL = new URL("../manifest.json", import.meta.url);
const state = globalThis.__WYB = { status: "loading", error: null, timings: {}, pyodide: null };
const started = performance.now();
const chunks = new Map();

async function fetchBytes(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Failed to fetch ${url}: ${response.status}`);
  return new Uint8Array(await response.arrayBuffer());
}

state.ready = (async () => {
  try {
    const response = await fetch(manifestURL, { cache: "no-cache" });
    if (!response.ok) throw new Error(`Manifest request failed: ${response.status}`);
    const config = await response.json();
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
    pyodide.globals.set("_wyb_entry", config.entry);
    await pyodide.runPythonAsync(`
import importlib, inspect
_wyb_module, _wyb_export = _wyb_entry.split(':', 1)
_wyb_result = getattr(importlib.import_module(_wyb_module), _wyb_export)()
if inspect.isawaitable(_wyb_result):
    await _wyb_result
from wybthon import flush
flush()
del _wyb_entry, _wyb_module, _wyb_export, _wyb_result
`);
    state.timings.application_ms = performance.now() - appStart;
    document.getElementById("wyb-loading")?.remove();
    state.status = "ready";
    state.timings.ready_ms = performance.now() - started;
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    state.timings.ready_frame_ms = performance.now() - started;
    globalThis.dispatchEvent(new CustomEvent("wybthon:ready", { detail: state.timings }));
    return state;
  } catch (error) {
    state.status = "error";
    state.error = String(error?.stack || error);
    const message = document.getElementById("wyb-loading");
    if (message) message.textContent = "The application couldn't start.";
    console.error(error);
    return state;
  }
})();
