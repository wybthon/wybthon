"""Batched DOM command buffer and rendering backends.

This module is the single point of contact between Wybthon's renderer
and the real DOM. Instead of calling DOM APIs directly (each call
crosses the Python-to-JS bridge in Pyodide), the reconciler and prop
appliers *emit* compact operations into a buffer. At well-defined
commit points (end of a render, end of an effect flush) the whole
buffer is serialized once and handed to a small JavaScript kernel that
applies every operation natively. A mount of a 1,000-row table becomes
one bridge crossing instead of tens of thousands.

Core concepts:

- **Node handles.** DOM nodes are referred to by integer ids allocated
  on the Python side. The kernel keeps an `id -> Node` registry, so no
  `JsProxy` objects flow through the hot path.
- **Ops.** Each operation is a small tuple, `(opcode, ...args)`,
  serialized as a JSON array. See the `OP_*` constants.
- **Backends.** [`BrowserBackend`][wybthon.kernel.BrowserBackend]
  drives the real DOM through the embedded JS kernel.
  [`PythonBackend`][wybthon.kernel.PythonBackend] is a reference
  interpreter that applies the same ops to any DOM-like stub document;
  it backs the unit tests and the stubbed benchmark so both exercise
  the exact protocol the browser sees.
- **Hydration.** `CLAIM_*` ops adopt server-rendered nodes in document
  order instead of creating them. Claims are tolerant: a node that
  doesn't match is created in place, and `HYDRATE_END` removes server
  nodes nobody claimed.
- **Events.** Event delegation lives in the kernel: one native listener
  per event type walks the ancestor chain natively and calls into
  Python once for the matching bubbling route with a JSON payload. See
  `wybthon.events` for the Python half.

Application code never imports this module directly; it's plumbing for
the reconciler, `wybthon.props`, and `wybthon.events`.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from typing import Any, Callable, Dict, List, Optional, Set

from . import diagnostics

__all__ = [
    "commit",
    "PythonBackend",
    "BrowserBackend",
    "set_backend",
    "reset",
]

# ---------------------------------------------------------------------------
# Op codes (wire protocol)
#
# Each op is a JSON array whose first element is the opcode. Node ids are
# integers allocated by ``alloc_id`` / ``alloc_ids``. ``None`` anchors mean
# "append".
# ---------------------------------------------------------------------------

OP_CREATE_ELEMENT = 1  # [op, id, tag]
OP_CREATE_TEXT = 2  # [op, id, text]
OP_CREATE_COMMENT = 3  # [op, id, data?]
OP_CLONE_TPL = 4  # [op, first_id, count, tpl_id]  (dense pre-order id block)
OP_INSERT = 5  # [op, parent_id, id, anchor_id_or_None]
OP_REMOVE = 6  # [op, id]
OP_SET_TEXT = 7  # [op, id, text]
OP_SET_ATTR = 8  # [op, id, name, value_or_None]  (None removes)
OP_SET_PROP = 9  # [op, id, name, value]  (DOM property assignment)
OP_SET_STYLE = 10  # [op, id, {prop: value_or_None}]  (kebab-case, None removes)
OP_LISTEN = 11  # [op, id, event_type]
OP_UNLISTEN = 12  # [op, id, event_type]
OP_RELEASE = 13  # [op, [ids...]]  (drop registry entries and listener sets)
OP_REGISTER_TPL = 14  # [op, tpl_id, html]  (parse once; cloned by OP_CLONE_TPL)
OP_CREATE_ELEMENT_NS = 15  # [op, id, namespace, tag]  (SVG / MathML)
OP_ROOT = 16  # [op, id]  (delegate events from this node instead of document)
OP_UNROOT = 17  # [op, id]
OP_MOVE_RANGE = 18  # [op, parent, first, last, anchor]
OP_REMOVE_RANGE = 19  # [op, first, last]
OP_RELEASE_TPL = 20  # [op, tpl_id]
OP_HOLE_TEXT = 21  # [op, anchor_id, text]  (reuse the anchor as visible text)
OP_HYDRATE = 22  # [op, root_id]  (start claiming server-rendered nodes under root)
OP_CLAIM_ELEMENT = 23  # [op, id, parent_id, tag, namespace_or_None]
OP_CLAIM_TEXT = 24  # [op, id, parent_id, text]
OP_CLAIM_COMMENT = 25  # [op, id, parent_id, data]
OP_HYDRATE_END = 26  # [op]  (remove unclaimed server nodes, stop claiming)

# ---------------------------------------------------------------------------
# Module state
# ---------------------------------------------------------------------------

# The op buffer. Hot paths append tuples directly via ``emit`` or a local
# alias of this list. ``commit`` drains it with ``clear`` (never rebinds)
# so aliases held by other modules stay valid across test reloads.
_ops: List[Any] = []

_next_id: int = 1

# Registered template skeletons: html -> tpl_id. The backend parses each
# skeleton once (OP_REGISTER_TPL) and clones it per mount (OP_CLONE_TPL).
# Bounded by the number of distinct static skeletons in the app.
_tpl_ids: OrderedDict[str, int] = OrderedDict()
_TEMPLATE_LIMIT = 256
_next_tpl_id: int = 1

_backend: Optional[Any] = None

# True while the reconciler mounts in hydration mode: mounts emit
# ``CLAIM_*`` ops that adopt server-rendered nodes instead of creating
# and inserting new ones. Only the synchronous initial mount of
# ``hydrate`` sets it; see ``wybthon.reconciler.hydrate``.
claiming: bool = False

# Dispatcher installed by ``wybthon.events`` (kernel can't import events;
# that would be circular). Signature: ``(node_id, event_type, payload_json)
# -> int flags`` where bit 1 stops delegated propagation and bit 2 calls
# ``preventDefault``.
_event_dispatcher: Optional[Callable[[int, str, str], int]] = None

FLAG_STOP_PROPAGATION = 1
FLAG_PREVENT_DEFAULT = 2


def alloc_id() -> int:
    """Allocate one fresh node id."""
    global _next_id
    nid = _next_id
    _next_id = nid + 1
    return nid


def alloc_ids(count: int) -> int:
    """Allocate a dense block of `count` ids; returns the first id."""
    global _next_id
    first = _next_id
    _next_id = first + count
    return first


def template_id(html: str) -> int:
    """Return the template id for `html`, registering it on first use.

    The registration op travels in the same batch as the clone that
    needs it, so no extra bridge crossing occurs.
    """
    tid = _tpl_ids.get(html)
    if tid is None:
        global _next_tpl_id
        tid = _next_tpl_id
        _next_tpl_id = tid + 1
        _tpl_ids[html] = tid
        _ops.append((OP_REGISTER_TPL, tid, html))
        if len(_tpl_ids) > _TEMPLATE_LIMIT:
            _, retired = _tpl_ids.popitem(last=False)
            _ops.append((OP_RELEASE_TPL, retired))
    else:
        _tpl_ids.move_to_end(html)
    return tid


def emit(op: Any) -> None:
    """Queue one op tuple for the next commit."""
    _ops.append(op)


def commit() -> None:
    """Flush all queued ops to the backend in one crossing.

    No-op when the buffer is empty. Safe to call at any time; the
    renderer calls it at the end of `render`, at the end of every
    effect flush, and before any synchronous DOM read.
    """
    if not _ops:
        return
    backend = _backend if _backend is not None else _ensure_backend()
    ops = list(_ops)
    _ops.clear()
    if diagnostics._active is not None:
        counts = diagnostics._active.counts
        counts["commits"] += 1
        counts["dom_ops"] += len(ops)
        for op in ops:
            counts[f"op_{op[0]}"] += 1
    backend.apply(ops)


def stats() -> dict[str, int]:
    """Return node, template, listener, root, and hydration-mismatch counts."""
    backend = _backend
    if backend is None:
        return {"nodes": 0, "templates": 0, "listeners": 0, "roots": 0, "hydration_mismatches": 0}
    if isinstance(backend, BrowserBackend):
        return json.loads(str(backend._kernel.stats()))
    return {
        "nodes": len(backend._nodes),
        "templates": len(backend._tpl_protos),
        "listeners": len(backend._listen),
        "roots": len(backend._roots),
        "hydration_mismatches": backend.hydration_mismatches,
    }


def take_state(node_id: int) -> Optional[str]:
    """Remove and return the serialized server state inside `node_id`, if any.

    Server renders end with a `<script type="application/json"
    data-wyb-state>` element. Commits pending ops first so the node
    exists.
    """
    commit()
    backend = _backend if _backend is not None else _ensure_backend()
    result = backend.take_state(node_id)
    return None if result is None else str(result)


def replay_events() -> int:
    """Replay input recorded before hydration through the delegated handlers.

    Returns the number of events replayed.
    """
    commit()
    backend = _backend if _backend is not None else _ensure_backend()
    return int(backend.replay() or 0)


def get_node(node_id: int) -> Any:
    """Return the raw DOM node for `node_id`, committing pending ops first."""
    commit()
    backend = _backend if _backend is not None else _ensure_backend()
    return backend.get_node(node_id)


def adopt(node: Any) -> int:
    """Register an existing raw DOM node and return its new id."""
    backend = _backend if _backend is not None else _ensure_backend()
    nid = alloc_id()
    return int(backend.adopt(nid, node))


def query(selector: str) -> Optional[int]:
    """Resolve a CSS selector to a node id, or `None` when nothing matches.

    Commits pending ops first so the selector can match nodes created
    earlier in the same logical update.
    """
    commit()
    backend = _backend if _backend is not None else _ensure_backend()
    nid = alloc_id()
    result = backend.query(nid, selector)
    return int(result) if result else None


def supports_html() -> bool:
    """Return whether the backend can parse templates (`OP_REGISTER_TPL`)."""
    backend = _backend if _backend is not None else _ensure_backend()
    return bool(backend.supports_html())


def current_event() -> Any:
    """Return the native event being dispatched right now, or `None`.

    Only valid synchronously inside an event handler; used as the
    escape hatch behind `DomEvent.raw`.
    """
    if _backend is None:
        return None
    return _backend.current_event()


def set_event_dispatcher(fn: Callable[[int, str, str], int]) -> None:
    """Install the Python-side event dispatcher (called by `wybthon.events`)."""
    global _event_dispatcher
    _event_dispatcher = fn
    if _backend is not None:
        _backend.set_dispatcher(fn)


def set_backend(backend: Any) -> None:
    """Install a rendering backend (tests pass a `PythonBackend`).

    Clears the template registry: a fresh backend has no registered
    skeletons, so they must be re-sent on next use.
    """
    global _backend
    _backend = backend
    _tpl_ids.clear()
    if _event_dispatcher is not None:
        backend.set_dispatcher(_event_dispatcher)


def reset(backend: Optional[Any] = None) -> None:
    """Test helper: clear the op buffer, id counters, and template registry."""
    global _next_id, _next_tpl_id, _backend
    _ops.clear()
    _next_id = 1
    _next_tpl_id = 1
    _tpl_ids.clear()
    _backend = None
    if backend is not None:
        set_backend(backend)


def _ensure_backend() -> Any:
    """Create the browser backend on first use, or fail with a clear error."""
    global _backend
    if _backend is None:
        try:
            set_backend(BrowserBackend())
        except Exception as exc:
            raise RuntimeError(
                "Wybthon has no rendering backend. In the browser this is "
                "created automatically; in tests install one with "
                "wybthon.kernel.set_backend(PythonBackend(document))."
            ) from exc
    return _backend


# ---------------------------------------------------------------------------
# JavaScript kernel
#
# A single IIFE evaluated once in the page. It owns the id -> Node registry,
# the registered-template protos for OP_CLONE_TPL, and native event
# delegation. The Python side talks to it through ``apply(json)`` plus a
# handful of synchronous helpers.
# ---------------------------------------------------------------------------

_KERNEL_JS = r"""
(() => {
  const nodes = new Map();          // id -> Node
  const directListeners = new Map(); // id -> Map<eventKey, {type, fn, options}>
  const nonBubbling = new Set([
    "focus", "blur", "mouseenter", "mouseleave", "pointerenter", "pointerleave",
    "scroll", "load", "error", "invalid", "toggle"
  ]);
  const listenTypes = new Map();    // id -> Set<eventType>
  const typeCounts = new Map();     // eventType -> number of listening nodes
  const rootListeners = new Map();  // eventType -> native listener
  const roots = new Map();          // delegation root -> refcount (document when empty)
  const tplProtos = new Map();      // tpl_id -> parsed root node (cloned per mount)
  let dispatcher = null;            // Python callback (id, type, payloadJson) -> flags
  let currentEvent = null;
  // Claim state while adopting server-rendered DOM (null otherwise).
  let hydrating = null;
  let hydrationMismatches = 0;

  const doc = document;

  function reg(id, node) {
    nodes.set(id, node);
    node.__wybId = id;
  }

  function delegationTargets() {
    return roots.size ? Array.from(roots.keys()) : [doc];
  }

  // Roots are refcounted: a render root and a Portal target may be the
  // same node, and each owner roots and unroots it independently.
  function addRoot(node) {
    const count = roots.get(node);
    if (count !== undefined) { roots.set(node, count + 1); return; }
    const wasEmpty = roots.size === 0;
    roots.set(node, 1);
    for (const [type, fn] of rootListeners) {
      if (wasEmpty) doc.removeEventListener(type, fn);
      node.addEventListener(type, fn);
    }
  }

  function removeRoot(node) {
    const count = roots.get(node);
    if (count === undefined) return;
    if (count > 1) { roots.set(node, count - 1); return; }
    roots.delete(node);
    for (const [type, fn] of rootListeners) {
      node.removeEventListener(type, fn);
      if (roots.size === 0) doc.addEventListener(type, fn);
    }
  }

  // Pre-order walk registering a dense id block; must match the order the
  // Python serializer counts nodes in (element, then children left to right).
  function walkAssign(root, firstId, count) {
    let id = firstId;
    let n = root;
    while (n) {
      reg(id, n);
      id++;
      if (n.firstChild) n = n.firstChild;
      else {
        while (n !== root && !n.nextSibling) n = n.parentNode;
        if (n === root) break;
        n = n.nextSibling;
      }
    }
    if (id - firstId !== count) {
      throw new Error(
        `wybthon kernel: template node count mismatch (expected ${count}, got ${id - firstId})`
      );
    }
  }

  function registerTpl(tplId, html) {
    const tpl = doc.createElement("template");
    tpl.innerHTML = html;
    const proto = tpl.content.firstChild;
    proto.remove();
    tplProtos.set(tplId, proto);
  }

  function cloneTpl(firstId, count, tplId) {
    const root = tplProtos.get(tplId).cloneNode(true);
    walkAssign(root, firstId, count);
  }

  // -- hydration --------------------------------------------------------
  // Each parent keeps a cursor: the next server node a claim may adopt.
  // Claims are tolerant: a node that doesn't match is created in place,
  // and HYDRATE_END removes server nodes nobody claimed.
  function isBlank(n) { return n.nodeType === 3 && !/\S/.test(n.nodeValue); }
  function cursorOf(parent) {
    hydrating.touched.add(parent);
    const c = hydrating.cursors.get(parent);
    return c === undefined ? parent.firstChild : c;
  }
  function mismatch(detail) {
    hydrationMismatches++;
    if (hydrating.mismatches++ < 5) console.warn(`Wybthon hydration mismatch: ${detail}`);
  }
  function describe(n) {
    if (!n) return "nothing";
    if (n.nodeType === 1) return `<${n.localName}>`;
    if (n.nodeType === 3) return `text ${JSON.stringify(n.nodeValue.slice(0, 40))}`;
    return "a comment";
  }
  function claimElement(id, parentId, tag, ns) {
    const parent = nodes.get(parentId);
    let c = cursorOf(parent);
    while (c && isBlank(c)) c = c.nextSibling;
    if (c && c.nodeType === 1 && c.localName.toLowerCase() === tag.toLowerCase()) {
      hydrating.cursors.set(parent, c.nextSibling);
      reg(id, c);
      return;
    }
    mismatch(`expected <${tag}>, found ${describe(c)}`);
    const node = ns ? doc.createElementNS(ns, tag) : doc.createElement(tag);
    parent.insertBefore(node, c || null);
    hydrating.cursors.set(parent, c || null);
    reg(id, node);
  }
  function claimText(id, parentId, text) {
    const parent = nodes.get(parentId);
    const c = cursorOf(parent);
    if (text !== "" && c && c.nodeType === 3) {
      const data = c.nodeValue;
      if (data === text) {
        hydrating.cursors.set(parent, c.nextSibling);
      } else if (data.startsWith(text)) {
        // The HTML parser merged adjacent text nodes; split ours off.
        hydrating.cursors.set(parent, c.splitText(text.length));
      } else {
        mismatch(`expected text ${JSON.stringify(text.slice(0, 40))}, found ${describe(c)}`);
        c.nodeValue = text;
        hydrating.cursors.set(parent, c.nextSibling);
      }
      reg(id, c);
      return;
    }
    // Empty text never survives HTML parsing, so it's always created.
    if (text !== "") mismatch(`expected text ${JSON.stringify(text.slice(0, 40))}, found ${describe(c)}`);
    const node = doc.createTextNode(text);
    parent.insertBefore(node, c || null);
    hydrating.cursors.set(parent, c || null);
    reg(id, node);
  }
  function claimComment(id, parentId, data) {
    const parent = nodes.get(parentId);
    let c = cursorOf(parent);
    while (c && isBlank(c)) c = c.nextSibling;
    if (c && c.nodeType === 8 && c.nodeValue === data) {
      hydrating.cursors.set(parent, c.nextSibling);
      reg(id, c);
      return;
    }
    if (data.startsWith("/")) {
      // A keyed end marker resynchronizes: server nodes before it were
      // never claimed (a boundary rendered differently on the server).
      for (let n = c; n; n = n.nextSibling) {
        if (n.nodeType === 8 && n.nodeValue === data) {
          mismatch(`unclaimed server content before ${data}`);
          while (c !== n) { const next = c.nextSibling; parent.removeChild(c); c = next; }
          hydrating.cursors.set(parent, n.nextSibling);
          reg(id, n);
          return;
        }
      }
    }
    mismatch(`expected a comment, found ${describe(c)}`);
    const node = doc.createComment(data);
    parent.insertBefore(node, c || null);
    hydrating.cursors.set(parent, c || null);
    reg(id, node);
  }
  function endHydration() {
    const { root, cursors, touched, fresh } = hydrating;
    for (const parent of touched) {
      if (parent !== root && !root.contains(parent)) continue;
      let n = cursors.has(parent) ? cursors.get(parent) : parent.firstChild;
      while (n) {
        const next = n.nextSibling;
        if (!fresh.has(n) && n.__wybId === undefined) parent.removeChild(n);
        n = next;
      }
    }
    hydrating = null;
  }
  function takeState(id) {
    const root = nodes.get(id);
    if (!root) return null;
    for (let n = root.lastChild; n; n = n.previousSibling) {
      if (n.nodeType === 1 && n.localName === "script" && n.hasAttribute("data-wyb-state")) {
        const text = n.textContent;
        n.remove();
        return text;
      }
    }
    return null;
  }
  // Replays input recorded by the bootstrap before hydration finished.
  function replay() {
    const queue = globalThis.__wybQueue;
    globalThis.__wybQueue = null;
    if (!queue) return 0;
    let count = 0;
    for (const entry of queue) {
      const ev = entry.event;
      const target = ev.target;
      if (!target || !target.isConnected) continue;
      if (entry.value !== undefined && "value" in target) target.value = entry.value;
      if (entry.checked !== undefined && "checked" in target) target.checked = entry.checked;
      const fn = rootListeners.get(ev.type);
      if (fn) { fn(ev); count++; }
    }
    return count;
  }

  function listen(id, key, options = {}) {
    const type = key.endsWith(":capture") ? key.slice(0, -8) : key;
    if (options.capture || options.passive || nonBubbling.has(type)) {
      let entries = directListeners.get(id);
      if (!entries) { entries = new Map(); directListeners.set(id, entries); }
      if (entries.has(key)) return;
      const fn = (ev) => {
        if (dispatcher === null) return;
        const saved = currentEvent;
        currentEvent = ev;
        try {
          const flags = dispatcher(id, key, buildPayload(ev));
          if (flags & 2) ev.preventDefault();
          if (flags & 1) ev.stopPropagation();
        } finally { currentEvent = saved; }
      };
      entries.set(key, {type, fn, options});
      nodes.get(id).addEventListener(type, fn, options);
      return;
    }
    let set = listenTypes.get(id);
    if (set === undefined) {
      set = new Set();
      listenTypes.set(id, set);
    }
    if (set.has(type)) return;
    set.add(type);
    const n = (typeCounts.get(type) || 0) + 1;
    typeCounts.set(type, n);
    if (n === 1) installRoot(type);
  }

  function unlisten(id, key) {
    const entries = directListeners.get(id);
    const entry = entries && entries.get(key);
    if (entry) {
      const node = nodes.get(id);
      if (node) node.removeEventListener(entry.type, entry.fn, entry.options);
      entries.delete(key);
      if (!entries.size) directListeners.delete(id);
      return;
    }
    const type = key;
    const set = listenTypes.get(id);
    if (set === undefined || !set.has(type)) return;
    set.delete(type);
    if (set.size === 0) listenTypes.delete(id);
    dropTypeCount(type);
  }

  function dropTypeCount(type) {
    const n = (typeCounts.get(type) || 0) - 1;
    if (n <= 0) {
      typeCounts.delete(type);
      const l = rootListeners.get(type);
      if (l !== undefined) {
        for (const target of delegationTargets()) target.removeEventListener(type, l);
        rootListeners.delete(type);
      }
    } else {
      typeCounts.set(type, n);
    }
  }

  const controlledSelects = new Map();
  function release(ids) {
    for (let i = 0; i < ids.length; i++) {
      const id = ids[i];
      controlledSelects.delete(id);
      const entries = directListeners.get(id);
      if (entries) for (const key of Array.from(entries.keys())) unlisten(id, key);
      const node = nodes.get(id);
      if (node && node.__wybId === id) delete node.__wybId;
      nodes.delete(id);
      const set = listenTypes.get(id);
      if (set !== undefined) {
        listenTypes.delete(id);
        for (const type of set) dropTypeCount(type);
      }
    }
  }

  function buildPayload(ev, route = undefined) {
    const path = ev.composedPath ? ev.composedPath() : [];
    const t = path.length ? path[0] : ev.target;
    let detail = ev.detail;
    try { detail = detail === undefined ? null : JSON.parse(JSON.stringify(detail)); }
    catch (_) { detail = null; }
    return JSON.stringify({
      route, detail,
      defaultPrevented: !!ev.defaultPrevented,
      isComposing: !!ev.isComposing,
      scrollTop: t && t.scrollTop !== undefined ? t.scrollTop : 0,
      selectedValues: t && t.selectedOptions ? Array.from(t.selectedOptions, option => option.value) : [],
      type: ev.type,
      value: t && t.value !== undefined ? t.value : null,
      checked: t && t.checked !== undefined ? !!t.checked : false,
      key: ev.key !== undefined ? ev.key : null,
      code: ev.code !== undefined ? ev.code : null,
      altKey: !!ev.altKey,
      ctrlKey: !!ev.ctrlKey,
      metaKey: !!ev.metaKey,
      shiftKey: !!ev.shiftKey,
      button: ev.button !== undefined ? ev.button : 0,
      clientX: ev.clientX !== undefined ? ev.clientX : 0,
      clientY: ev.clientY !== undefined ? ev.clientY : 0,
      targetId: t && t.__wybId !== undefined ? t.__wybId : null,
    });
  }

  function installRoot(type) {
    const fn = (ev) => {
      if (dispatcher === null) return;
      // Nested roots (a portal inside the app root) see the same event
      // as it bubbles; only the innermost root dispatches it.
      if (ev.__wybHandled) return;
      ev.__wybHandled = true;
      const route = [];
      const path = ev.composedPath ? ev.composedPath() : [];
      if (!path.length) for (let node = ev.target; node; node = node.parentNode) path.push(node);
      for (const node of path) {
        const id = node.__wybId;
        const set = id === undefined ? undefined : listenTypes.get(id);
        if (set && set.has(type)) route.push([id, type]);
      }
      if (!route.length) return;
      const saved = currentEvent;
      currentEvent = ev;
      try {
        const flags = dispatcher(0, type, buildPayload(ev, route));
        if (flags & 2) ev.preventDefault();
        if (flags & 1) ev.stopPropagation();
      } finally { currentEvent = saved; }
    };
    for (const target of delegationTargets()) target.addEventListener(type, fn);
    rootListeners.set(type, fn);
  }

  function apply(opsJson) {
    const ops = JSON.parse(opsJson);
    for (let i = 0; i < ops.length; i++) {
      const op = ops[i];
      switch (op[0]) {
        case 1: { // CREATE_ELEMENT
          reg(op[1], doc.createElement(op[2]));
          break;
        }
        case 2: { // CREATE_TEXT
          reg(op[1], doc.createTextNode(op[2]));
          break;
        }
        case 3: { // CREATE_COMMENT
          reg(op[1], doc.createComment(op[2] || ""));
          break;
        }
        case 4: { // CLONE_TPL
          cloneTpl(op[1], op[2], op[3]);
          break;
        }
        case 5: { // INSERT
          // The anchor's live parent wins over op[1]: a subtree parked
          // off-document by a Loading boundary keeps receiving updates
          // addressed to its original parent.
          const anchor = op[3] === null ? undefined : nodes.get(op[3]);
          const inserted = nodes.get(op[2]);
          if (hydrating !== null) hydrating.fresh.add(inserted);
          if (anchor !== undefined && anchor.parentNode !== null) {
            anchor.parentNode.insertBefore(inserted, anchor);
          } else {
            nodes.get(op[1]).appendChild(inserted);
          }
          break;
        }
        case 6: { // REMOVE
          const n = nodes.get(op[1]);
          if (n !== undefined && n.parentNode !== null) n.parentNode.removeChild(n);
          break;
        }
        case 7: { // SET_TEXT
          nodes.get(op[1]).nodeValue = op[2];
          break;
        }
        case 8: { // SET_ATTR
          const n = nodes.get(op[1]);
          if (op[3] === null) n.removeAttribute(op[2]);
          else n.setAttribute(op[2], op[3]);
          break;
        }
        case 9: { // SET_PROP
          const node = nodes.get(op[1]);
          if (node.localName === "select" && (op[2] === "value" || op[2] === "selectedValues")) {
            controlledSelects.set(op[1], [op[2], op[3]]);
          } else if (node[op[2]] !== op[3]) node[op[2]] = op[3];
          break;
        }
        case 10: { // SET_STYLE
          const style = nodes.get(op[1]).style;
          const decls = op[2];
          for (const k in decls) {
            const v = decls[k];
            if (v === null) style.removeProperty(k);
            else style.setProperty(k, v);
          }
          break;
        }
        case 11: { // LISTEN
          listen(op[1], op[2], op[3]);
          break;
        }
        case 12: { // UNLISTEN
          unlisten(op[1], op[2]);
          break;
        }
        case 13: { // RELEASE
          release(op[1]);
          break;
        }
        case 14: { // REGISTER_TPL
          registerTpl(op[1], op[2]);
          break;
        }
        case 15: { // CREATE_ELEMENT_NS
          reg(op[1], doc.createElementNS(op[2], op[3]));
          break;
        }
        case 16: { // ROOT
          const n = nodes.get(op[1]);
          if (n !== undefined) addRoot(n);
          break;
        }
        case 17: { // UNROOT
          const n = nodes.get(op[1]);
          if (n !== undefined) removeRoot(n);
          break;
        }
        case 21: { // HOLE_TEXT
          const node = nodes.get(op[1]);
          if (node.nodeType === 3) node.nodeValue = op[2];
          else {
            const text = doc.createTextNode(op[2]);
            if (node.parentNode) node.parentNode.replaceChild(text, node);
            reg(op[1], text);
          }
          break;
        }
        case 22: { // HYDRATE
          hydrating = {
            root: nodes.get(op[1]), cursors: new Map(), touched: new Set(), fresh: new Set(), mismatches: 0,
          };
          break;
        }
        case 23: { // CLAIM_ELEMENT
          claimElement(op[1], op[2], op[3], op[4]);
          break;
        }
        case 24: { // CLAIM_TEXT
          claimText(op[1], op[2], op[3]);
          break;
        }
        case 25: { // CLAIM_COMMENT
          claimComment(op[1], op[2], op[3]);
          break;
        }
        case 26: { // HYDRATE_END
          if (hydrating !== null) endHydration();
          break;
        }
        case 20: { // RELEASE_TPL
          tplProtos.delete(op[1]);
          break;
        }
        case 18: { // MOVE_RANGE
          const first = nodes.get(op[2]), last = nodes.get(op[3]);
          const anchor = op[4] === null ? null : nodes.get(op[4]);
          const parent = anchor && anchor.parentNode ? anchor.parentNode : nodes.get(op[1]);
          if (!first || !last || anchor === first || (last.parentNode === parent && last.nextSibling === anchor)) break;
          const fragment = doc.createDocumentFragment();
          const after = last.nextSibling;
          let current = first;
          while (current && current !== after) {
            const next = current.nextSibling;
            fragment.appendChild(current);
            current = next;
          }
          parent.insertBefore(fragment, anchor);
          break;
        }
        case 19: { // REMOVE_RANGE
          const first = nodes.get(op[1]), last = nodes.get(op[2]);
          if (!first || !last) break;
          if (first !== last && first.parentNode !== null && first.parentNode === last.parentNode) {
            // One native range deletion instead of a removal per node
            // (clearing a 10,000-row list emits a single range).
            const range = doc.createRange();
            range.setStartBefore(first);
            range.setEndAfter(last);
            range.deleteContents();
            break;
          }
          const after = last.nextSibling;
          let current = first;
          while (current && current !== after) {
            const next = current.nextSibling;
            if (current.parentNode) current.parentNode.removeChild(current);
            current = next;
          }
          break;
        }
        default:
          throw new Error(`wybthon kernel: unknown op ${op[0]}`);
      }
    }
    // Options may be inserted after the select's property op, or in a later
    // commit. Reapply controlled selection once all structural ops finish.
    for (const [id, [prop, value]] of controlledSelects) {
      const node = nodes.get(id);
      if (prop === "selectedValues") {
        const selected = new Set(value || []);
        for (const option of node.options) option.selected = selected.has(option.value);
      } else if (node.value !== value) node.value = value;
    }

  }

  return {
    apply,
    getNode: (id) => nodes.get(id),
    adopt: (id, node) => {
      if (node.__wybId !== undefined && nodes.get(node.__wybId) === node) return node.__wybId;
      reg(id, node); return id;
    },
    adoptQuery: (id, selector) => {
      const n = doc.querySelector(selector);
      if (n === null) return 0;
      if (n.__wybId !== undefined && nodes.get(n.__wybId) === n) return n.__wybId;
      reg(id, n);
      return id;
    },
    setDispatcher: (fn) => { dispatcher = fn; },
    getCurrentEvent: () => currentEvent,
    takeState,
    replay,
    stats: () => JSON.stringify({
      nodes: nodes.size,
      listeners: listenTypes.size + directListeners.size,
      roots: roots.size,
      types: typeCounts.size,
      templates: tplProtos.size,
      hydration_mismatches: hydrationMismatches,
    }),
  };
})()
"""


class _ClaimState:
    """Per-hydration claim cursors for the reference backend."""

    __slots__ = ("root", "cursors", "touched", "fresh", "mismatches")

    def __init__(self, root: Any) -> None:
        self.root = root
        self.cursors: dict[int, Any] = {}
        self.touched: dict[int, Any] = {}
        self.fresh: set[int] = set()
        self.mismatches = 0


def _is_comment(node: Any) -> bool:
    return bool(getattr(node, "_is_comment", False))


def _is_text(node: Any) -> bool:
    return bool(getattr(node, "_is_text", False)) and not _is_comment(node)


def _is_element(node: Any) -> bool:
    return getattr(node, "tag", None) is not None and not _is_comment(node) and not _is_text(node)


def _is_blank(node: Any) -> bool:
    return _is_text(node) and not str(node.nodeValue or "").strip()


def _contains(root: Any, node: Any) -> bool:
    while node is not None:
        if node is root:
            return True
        node = getattr(node, "parentNode", None)
    return False


class BrowserBackend:
    """Backend that drives the real DOM through the embedded JS kernel.

    Created automatically on first use inside Pyodide. Every `apply`
    serializes the op list to JSON and makes exactly one call across
    the bridge.
    """

    def __init__(self) -> None:
        self._kernel = self._eval_kernel()
        self._dispatch_proxy: Any = None

    @staticmethod
    def _eval_kernel() -> Any:
        try:
            from pyodide.code import run_js

            return run_js(_KERNEL_JS)
        except ImportError:
            import js

            return js.eval(_KERNEL_JS)

    def apply(self, ops: List[Any]) -> None:
        """Serialize `ops` to JSON and apply them in one kernel call."""
        measured = diagnostics._active
        if measured is None:
            self._kernel.apply(json.dumps(ops, separators=(",", ":"), ensure_ascii=False))
            return
        from time import perf_counter

        started = perf_counter()
        encoded = json.dumps(ops, separators=(",", ":"), ensure_ascii=False)
        serialized = perf_counter()
        self._kernel.apply(encoded)
        finished = perf_counter()
        measured.counts["serialized_bytes"] += len(encoded.encode("utf-8"))
        measured.counts["serialize_us"] += round((serialized - started) * 1000000)
        measured.counts["kernel_us"] += round((finished - serialized) * 1000000)

    def get_node(self, node_id: int) -> Any:
        """Return the raw DOM node registered under `node_id`."""
        return self._kernel.getNode(node_id)

    def adopt(self, node_id: int, node: Any) -> int:
        """Return an existing handle or register the node under `node_id`."""
        return int(self._kernel.adopt(node_id, node))

    def query(self, node_id: int, selector: str) -> int | None:
        """Return the canonical handle of a selector match, or None."""
        result = self._kernel.adoptQuery(node_id, selector)
        return int(result) if result else None

    def supports_html(self) -> bool:
        """The browser can always parse template HTML."""
        return True

    def set_dispatcher(self, fn: Callable[[int, str, str], int]) -> None:
        """Install the Python event dispatcher as the kernel's callback proxy."""
        from pyodide.ffi import create_proxy

        if self._dispatch_proxy is not None:
            try:
                self._dispatch_proxy.destroy()
            except Exception:
                pass
        self._dispatch_proxy = create_proxy(fn)
        self._kernel.setDispatcher(self._dispatch_proxy)

    def current_event(self) -> Any:
        """Return the native event currently being dispatched, or `None`."""
        return self._kernel.getCurrentEvent()

    def take_state(self, node_id: int) -> Any:
        """Remove and return the text of the server state script under `node_id`."""
        return self._kernel.takeState(node_id)

    def replay(self) -> int:
        """Replay input the bootstrap recorded before hydration."""
        return int(self._kernel.replay())


class PythonBackend:
    """Reference op interpreter over a DOM-like stub document.

    Mirrors the JS kernel's semantics against plain Python objects that
    quack like DOM nodes (the test suite's `StubNode` and the benchmark
    runner's `_Node`). Unit tests and the stubbed benchmark run the real
    wire protocol through this class, so protocol bugs surface without
    a browser.
    """

    def __init__(self, document: Any) -> None:
        self._doc = document
        self._nodes: Dict[int, Any] = {}
        self._controlled_selects: dict[int, tuple[str, Any]] = {}
        self._listen: Dict[int, Set[str]] = {}
        self._listener_options: dict[tuple[int, str], dict[str, Any]] = {}
        self._type_counts: Dict[str, int] = {}
        self._root_listeners: Dict[str, Any] = {}
        self._roots: List[Any] = []
        self._root_counts: Dict[int, int] = {}
        self._dispatcher: Optional[Callable[[int, str, str], int]] = None
        self._current_event: Any = None
        self._tpl = self._probe_template(document)
        self._tpl_protos: Dict[int, Any] = {}
        self._hydrating: Optional[_ClaimState] = None
        self.hydration_mismatches = 0
        # Events recorded "before hydration" by tests: (event_type, target, payload).
        self.queued_events: list[tuple[str, Any, Optional[dict]]] = []

    @staticmethod
    def _probe_template(document: Any) -> Any:
        try:
            tpl = document.createElement("template")
            tpl.innerHTML = "<div>a</div>"
            first = tpl.content.firstChild
            if first is None or first.firstChild is None:
                return None
            tpl.innerHTML = ""
            return tpl
        except Exception:
            return None

    # -- protocol ----------------------------------------------------------

    def apply(self, ops: List[Any]) -> None:
        """Interpret a batch of ops against the stub document."""
        nodes = self._nodes
        doc = self._doc
        for op in ops:
            code = op[0]
            if code == OP_CREATE_ELEMENT:
                self._reg(op[1], doc.createElement(op[2]))
            elif code == OP_CREATE_TEXT:
                self._reg(op[1], doc.createTextNode(op[2]))
            elif code == OP_CREATE_COMMENT:
                self._reg(op[1], doc.createComment(op[2] if len(op) > 2 else ""))
            elif code == OP_CLONE_TPL:
                self._clone_tpl(op[1], op[2], op[3])
            elif code == OP_INSERT:
                anchor = None if op[3] is None else nodes.get(op[3])
                anchor_parent = None if anchor is None else getattr(anchor, "parentNode", None)
                if self._hydrating is not None:
                    self._hydrating.fresh.add(id(nodes[op[2]]))
                if anchor_parent is not None:
                    anchor_parent.insertBefore(nodes[op[2]], anchor)
                else:
                    nodes[op[1]].appendChild(nodes[op[2]])
            elif code == OP_REMOVE:
                node = nodes.get(op[1])
                if node is not None and getattr(node, "parentNode", None) is not None:
                    node.parentNode.removeChild(node)
            elif code == OP_MOVE_RANGE:
                first, last = nodes.get(op[2]), nodes.get(op[3])
                anchor = nodes.get(op[4]) if op[4] is not None else None
                if first is None or last is None or anchor is first:
                    continue
                parent = getattr(anchor, "parentNode", None) if anchor is not None else None
                if parent is None:
                    parent = nodes[op[1]]
                if last.parentNode is parent and last.nextSibling is anchor:
                    continue
                after = last.nextSibling
                current = first
                moving = []
                while current is not None and current is not after:
                    moving.append(current)
                    current = current.nextSibling
                for node in moving:
                    parent.insertBefore(node, anchor)
            elif code == OP_REMOVE_RANGE:
                first, last = nodes.get(op[1]), nodes.get(op[2])
                if first is None or last is None:
                    continue
                after = last.nextSibling
                current = first
                while current is not None and current is not after:
                    following = current.nextSibling
                    if current.parentNode is not None:
                        current.parentNode.removeChild(current)
                    current = following
            elif code == OP_HOLE_TEXT:
                node = nodes[op[1]]
                if getattr(node, "_is_text", False) and not getattr(node, "_is_comment", False):
                    node.nodeValue = op[2]
                else:
                    text = doc.createTextNode(op[2])
                    if node.parentNode is not None:
                        node.parentNode.insertBefore(text, node)
                        node.parentNode.removeChild(node)
                    self._reg(op[1], text)
            elif code == OP_SET_TEXT:
                nodes[op[1]].nodeValue = op[2]
            elif code == OP_SET_ATTR:
                if op[3] is None:
                    nodes[op[1]].removeAttribute(op[2])
                else:
                    nodes[op[1]].setAttribute(op[2], op[3])
            elif code == OP_SET_PROP:
                node = nodes[op[1]]
                if (getattr(node, "tag", "") or "").lower() == "select" and op[2] in ("value", "selectedValues"):
                    self._controlled_selects[op[1]] = (op[2], op[3])
                else:
                    setattr(node, op[2], op[3])
            elif code == OP_SET_STYLE:
                style = nodes[op[1]].style
                for key, value in op[2].items():
                    if value is None:
                        style.removeProperty(key)
                    else:
                        style.setProperty(key, value)
            elif code == OP_LISTEN:
                self._listen_op(op[1], op[2])
                self._listener_options[(op[1], op[2])] = op[3] if len(op) > 3 else {}
            elif code == OP_UNLISTEN:
                self._unlisten_op(op[1], op[2])
            elif code == OP_RELEASE:
                self._release(op[1])
            elif code == OP_RELEASE_TPL:
                self._tpl_protos.pop(op[1], None)
            elif code == OP_REGISTER_TPL:
                self._register_tpl(op[1], op[2])
            elif code == OP_CREATE_ELEMENT_NS:
                create_ns = getattr(doc, "createElementNS", None)
                node = create_ns(op[2], op[3]) if create_ns is not None else doc.createElement(op[3])
                try:
                    node.namespaceURI = op[2]
                except Exception:
                    pass
                self._reg(op[1], node)
            elif code == OP_HYDRATE:
                self._hydrating = _ClaimState(nodes[op[1]])
            elif code == OP_CLAIM_ELEMENT:
                self._claim_element(op[1], op[2], op[3], op[4])
            elif code == OP_CLAIM_TEXT:
                self._claim_text(op[1], op[2], op[3])
            elif code == OP_CLAIM_COMMENT:
                self._claim_comment(op[1], op[2], op[3])
            elif code == OP_HYDRATE_END:
                if self._hydrating is not None:
                    self._end_hydration()
            elif code == OP_ROOT:
                self._add_root(nodes.get(op[1]))
            elif code == OP_UNROOT:
                self._remove_root(nodes.get(op[1]))
            else:
                raise ValueError(f"wybthon kernel: unknown op {code}")

        for node_id, (prop, value) in self._controlled_selects.items():
            node = nodes[node_id]
            setattr(node, prop, value)
            pending = list(node.childNodes)
            while pending:
                child = pending.pop()
                if (getattr(child, "tag", "") or "").lower() == "option":
                    option_value = getattr(child, "value", None) or child.getAttribute("value")
                    child.selected = (
                        option_value in (value or []) if prop == "selectedValues" else option_value == value
                    )
                pending.extend(child.childNodes)

    def get_node(self, node_id: int) -> Any:
        """Return the stub node registered under `node_id`, or `None`."""
        return self._nodes.get(node_id)

    def adopt(self, node_id: int, node: Any) -> int:
        """Return an existing handle or register this stub node."""
        current = getattr(node, "_wyb_id", None)
        if current is not None and self._nodes.get(current) is node:
            return int(current)
        self._reg(node_id, node)
        return node_id

    def query(self, node_id: int, selector: str) -> int | None:
        """Return the canonical handle of a selector match, or None."""
        node = self._doc.querySelector(selector)
        return None if node is None else self.adopt(node_id, node)

    def supports_html(self) -> bool:
        """Whether the stub document parses `<template>` innerHTML."""
        return self._tpl is not None

    def set_dispatcher(self, fn: Callable[[int, str, str], int]) -> None:
        """Install the Python event dispatcher used by `dispatch`."""
        self._dispatcher = fn

    def current_event(self) -> Any:
        """Return the raw event passed to the in-flight `dispatch`, or `None`."""
        return self._current_event

    def take_state(self, node_id: int) -> Optional[str]:
        """Remove and return the text of the server state script under `node_id`."""
        root = self._nodes.get(node_id)
        if root is None:
            return None
        for child in reversed(list(root.childNodes)):
            if _is_element(child) and child.tag == "script" and child.getAttribute("data-wyb-state") is not None:
                text = "".join(str(n.nodeValue or "") for n in child.childNodes)
                root.removeChild(child)
                return text
        return None

    def replay(self) -> int:
        """Replay `queued_events` (recorded "before hydration") through delegation."""
        queued, self.queued_events = self.queued_events, []
        for event_type, target, payload in queued:
            self.dispatch(event_type, target, payload=payload)
        return len(queued)

    # -- hydration ----------------------------------------------------------

    def _mismatch(self) -> None:
        self.hydration_mismatches += 1
        assert self._hydrating is not None
        self._hydrating.mismatches += 1

    def _cursor(self, parent: Any) -> Any:
        state = self._hydrating
        assert state is not None
        state.touched[id(parent)] = parent
        key = id(parent)
        return state.cursors[key] if key in state.cursors else parent.firstChild

    def _set_cursor(self, parent: Any, node: Any) -> None:
        assert self._hydrating is not None
        self._hydrating.cursors[id(parent)] = node

    def _claim_element(self, node_id: int, parent_id: int, tag: str, ns: Optional[str]) -> None:
        parent = self._nodes[parent_id]
        c = self._cursor(parent)
        while c is not None and _is_blank(c):
            c = c.nextSibling
        if c is not None and _is_element(c) and str(c.tag).lower() == tag.lower():
            self._set_cursor(parent, c.nextSibling)
            self._reg(node_id, c)
            return
        self._mismatch()
        create_ns = getattr(self._doc, "createElementNS", None)
        node = create_ns(ns, tag) if ns and create_ns is not None else self._doc.createElement(tag)
        parent.insertBefore(node, c)
        self._set_cursor(parent, c)
        self._reg(node_id, node)

    def _claim_text(self, node_id: int, parent_id: int, text: str) -> None:
        parent = self._nodes[parent_id]
        c = self._cursor(parent)
        if text and c is not None and _is_text(c):
            data = str(c.nodeValue or "")
            if data == text:
                self._set_cursor(parent, c.nextSibling)
            elif data.startswith(text):
                rest = self._doc.createTextNode(data[len(text) :])
                parent.insertBefore(rest, c.nextSibling)
                c.nodeValue = text
                self._set_cursor(parent, rest)
            else:
                self._mismatch()
                c.nodeValue = text
                self._set_cursor(parent, c.nextSibling)
            self._reg(node_id, c)
            return
        if text:
            self._mismatch()
        node = self._doc.createTextNode(text)
        parent.insertBefore(node, c)
        self._set_cursor(parent, c)
        self._reg(node_id, node)

    def _claim_comment(self, node_id: int, parent_id: int, data: str) -> None:
        parent = self._nodes[parent_id]
        c = self._cursor(parent)
        while c is not None and _is_blank(c):
            c = c.nextSibling
        if c is not None and _is_comment(c) and str(c.nodeValue or "") == data:
            self._set_cursor(parent, c.nextSibling)
            self._reg(node_id, c)
            return
        if data.startswith("/"):
            n = c
            while n is not None:
                if _is_comment(n) and str(n.nodeValue or "") == data:
                    self._mismatch()
                    while c is not n:
                        following = c.nextSibling
                        parent.removeChild(c)
                        c = following
                    self._set_cursor(parent, n.nextSibling)
                    self._reg(node_id, n)
                    return
                n = n.nextSibling
        self._mismatch()
        node = self._doc.createComment(data)
        parent.insertBefore(node, c)
        self._set_cursor(parent, c)
        self._reg(node_id, node)

    def _end_hydration(self) -> None:
        state = self._hydrating
        assert state is not None
        self._hydrating = None
        for key, parent in state.touched.items():
            if parent is not state.root and not _contains(state.root, parent):
                continue
            n = state.cursors[key] if key in state.cursors else parent.firstChild
            while n is not None:
                following = n.nextSibling
                if id(n) not in state.fresh and getattr(n, "_wyb_id", None) is None:
                    parent.removeChild(n)
                n = following

    # -- internals ----------------------------------------------------------

    def _reg(self, node_id: int, node: Any) -> None:
        self._nodes[node_id] = node
        try:
            node._wyb_id = node_id
        except Exception:
            pass

    def _register_tpl(self, tpl_id: int, html: str) -> None:
        tpl = self._tpl
        if tpl is None:
            raise RuntimeError("PythonBackend: document has no template support")
        tpl.innerHTML = html
        root = tpl.content.firstChild
        tpl.content.removeChild(root)
        self._tpl_protos[tpl_id] = root

    def _clone_tpl(self, first_id: int, count: int, tpl_id: int) -> None:
        root = self._clone_node(self._tpl_protos[tpl_id])
        node_id = first_id
        stack = [root]
        while stack:
            node = stack.pop()
            self._reg(node_id, node)
            node_id += 1
            kids = node.childNodes
            for i in range(len(kids) - 1, -1, -1):
                stack.append(kids[i])
        if node_id - first_id != count:
            raise RuntimeError(
                f"wybthon kernel: template node count mismatch (expected {count}, got {node_id - first_id})"
            )

    def _clone_node(self, node: Any) -> Any:
        """Structural deep copy through the stub document's factories.

        The equivalent of `Node.cloneNode(true)`, which DOM stubs don't
        implement. Class and style side-effects mirror what the stub
        HTML parsers apply when parsing attributes.
        """
        doc = self._doc
        if getattr(node, "tag", None) is None:
            text = node.nodeValue
            if getattr(node, "_is_comment", False):
                return doc.createComment("" if text is None else text)
            return doc.createTextNode("" if text is None else text)
        clone = doc.createElement(node.tag)
        attrs = getattr(node, "attributes", None)
        if attrs:
            for name, value in attrs.items():
                clone.setAttribute(name, value)
            class_attr = attrs.get("class")
            if class_attr:
                class_list = getattr(clone, "classList", None)
                if class_list is not None:
                    for cls in class_attr.split():
                        class_list.add(cls)
            style_attr = attrs.get("style")
            if style_attr:
                style = getattr(clone, "style", None)
                if style is not None:
                    for decl in style_attr.split(";"):
                        if ":" in decl:
                            key, value = decl.split(":", 1)
                            style.setProperty(key.strip(), value.strip())
        for child in node.childNodes:
            clone.appendChild(self._clone_node(child))
        return clone

    def _listen_op(self, node_id: int, event_type: str) -> None:
        types = self._listen.setdefault(node_id, set())
        if event_type in types:
            return
        types.add(event_type)
        count = self._type_counts.get(event_type, 0) + 1
        self._type_counts[event_type] = count
        if count == 1:
            self._install_root(event_type)

    def _unlisten_op(self, node_id: int, event_type: str) -> None:
        types = self._listen.get(node_id)
        if types is None or event_type not in types:
            return
        types.discard(event_type)
        self._listener_options.pop((node_id, event_type), None)
        if not types:
            self._listen.pop(node_id, None)
        self._drop_type_count(event_type)

    def _drop_type_count(self, event_type: str) -> None:
        count = self._type_counts.get(event_type, 0) - 1
        if count <= 0:
            self._type_counts.pop(event_type, None)
            listener = self._root_listeners.pop(event_type, None)
            if listener is not None:
                try:
                    self._doc.removeEventListener(event_type, listener)
                except Exception:
                    pass
        else:
            self._type_counts[event_type] = count

    def _release(self, ids: List[int]) -> None:
        for node_id in ids:
            self._controlled_selects.pop(node_id, None)
            node = self._nodes.pop(node_id, None)
            if node is not None and getattr(node, "_wyb_id", None) == node_id:
                delattr(node, "_wyb_id")
            types = self._listen.pop(node_id, None)
            if types:
                for event_type in types:
                    self._listener_options.pop((node_id, event_type), None)
                    self._drop_type_count(event_type)

    def _targets(self) -> list[Any]:
        return list(self._roots) if self._roots else [self._doc]

    def _install_root(self, event_type: str) -> None:
        def listener(event: Any) -> None:
            self.dispatch(event_type, getattr(event, "target", None), event)

        for target in self._targets():
            try:
                target.addEventListener(event_type, listener)
            except Exception:
                pass
        self._root_listeners[event_type] = listener

    def _add_root(self, node: Any) -> None:
        if node is None:
            return
        # Refcounted like the JS kernel: a render root and a Portal target
        # may be the same node.
        if node in self._roots:
            self._root_counts[id(node)] += 1
            return
        was_empty = not self._roots
        self._roots.append(node)
        self._root_counts[id(node)] = 1
        for event_type, listener in self._root_listeners.items():
            try:
                if was_empty:
                    self._doc.removeEventListener(event_type, listener)
                node.addEventListener(event_type, listener)
            except Exception:
                pass

    def _remove_root(self, node: Any) -> None:
        if node is None or node not in self._roots:
            return
        remaining = self._root_counts[id(node)] - 1
        if remaining > 0:
            self._root_counts[id(node)] = remaining
            return
        del self._root_counts[id(node)]
        self._roots.remove(node)
        for event_type, listener in self._root_listeners.items():
            try:
                node.removeEventListener(event_type, listener)
                if not self._roots:
                    self._doc.addEventListener(event_type, listener)
            except Exception:
                pass

    def roots(self) -> list[Any]:
        """Return the registered delegation roots (test helper)."""
        return list(self._roots)

    # -- test helper ---------------------------------------------------------

    def dispatch(self, event_type: str, target: Any, raw_event: Any = None, payload: Optional[dict] = None) -> None:
        """Simulate a bubbling native event dispatch for tests.

        Walks the stub-node ancestor chain from `target`, invoking the
        Python dispatcher for every registered `(node, event_type)`
        handler, exactly like the JS kernel's root listener.
        """
        if self._dispatcher is None:
            return
        base = {
            "type": event_type,
            "value": getattr(target, "value", None),
            "scrollTop": getattr(target, "scrollTop", 0),
            "selectedValues": getattr(target, "selectedValues", []),
            "checked": bool(getattr(target, "checked", False)),
            "key": None,
            "code": None,
            "altKey": False,
            "ctrlKey": False,
            "metaKey": False,
            "shiftKey": False,
            "button": 0,
            "clientX": 0,
            "clientY": 0,
            "targetId": getattr(target, "_wyb_id", None),
        }
        if payload:
            base.update(payload)
        path = []
        node = target
        while node is not None:
            path.append(node)
            node = getattr(node, "parentNode", None)
        route = []
        non_bubbling = event_type in {
            "focus",
            "blur",
            "mouseenter",
            "mouseleave",
            "pointerenter",
            "pointerleave",
            "scroll",
            "load",
            "error",
            "invalid",
            "toggle",
        }
        for node in reversed(path):
            nid = getattr(node, "_wyb_id", None)
            key = event_type + ":capture"
            if nid is not None and key in self._listen.get(nid, ()):
                route.append([nid, key])
        for node in path[:1] if non_bubbling else path:
            nid = getattr(node, "_wyb_id", None)
            if nid is not None and event_type in self._listen.get(nid, ()):
                route.append([nid, event_type])
        base["route"] = route
        previous_event = self._current_event
        self._current_event = raw_event
        try:
            flags = self._dispatcher(0, event_type, json.dumps(base))
            if raw_event is not None:
                if flags & FLAG_PREVENT_DEFAULT and hasattr(raw_event, "preventDefault"):
                    raw_event.preventDefault()
                if flags & FLAG_STOP_PROPAGATION and hasattr(raw_event, "stopPropagation"):
                    raw_event.stopPropagation()
        finally:
            self._current_event = previous_event
