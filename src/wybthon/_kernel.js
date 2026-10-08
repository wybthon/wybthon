// Wybthon's DOM kernel.
//
// Evaluated once per page. It owns the id -> Node registry, the parsed
// template prototypes, and native event delegation. Python sends batches of
// JSON-encoded commands through `apply`; see `wybthon/kernel.py` for the wire
// protocol. The expression's value is the kernel object.
(() => {
  const nodes = new Map();          // id -> Node
  const directListeners = new Map(); // id -> Map<eventKey, {type, fn, options}>
  const nonBubbling = new Set([
    "focus", "blur", "mouseenter", "mouseleave", "pointerenter", "pointerleave",
    "scroll", "load", "error", "invalid", "toggle"
  ]);
  const typeCounts = new Map();     // eventType -> number of listening nodes
  const rootListeners = new Map();  // eventType -> native listener
  const roots = new Map();          // delegation root -> refcount (document when empty)
  // tpl_id -> {proto, count, texts: [offsets], listens: [[offset, type], ...]}
  const templates = new Map();
  const controlledSelects = new Map();
  let delegatedNodes = 0;           // nodes with at least one delegated listener
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

  // -- delegation roots ---------------------------------------------------

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

  // -- delegated listeners ------------------------------------------------
  // A node's delegated event types live on the node itself (`__wybL`): a
  // string for the common single type, upgraded to a Set for several.

  function hasType(node, type) {
    const l = node.__wybL;
    return l !== undefined && (l === type || (typeof l !== "string" && l.has(type)));
  }

  function addType(node, type) {
    const l = node.__wybL;
    if (l === undefined) {
      node.__wybL = type;
      delegatedNodes++;
    } else if (typeof l === "string") {
      if (l === type) return;
      node.__wybL = new Set([l, type]);
    } else {
      if (l.has(type)) return;
      l.add(type);
    }
    const n = (typeCounts.get(type) || 0) + 1;
    typeCounts.set(type, n);
    if (n === 1) installRoot(type);
  }

  function removeType(node, type) {
    const l = node.__wybL;
    if (l === undefined) return;
    if (typeof l === "string") {
      if (l !== type) return;
      delete node.__wybL;
      delegatedNodes--;
    } else {
      if (!l.delete(type)) return;
      if (l.size === 0) { delete node.__wybL; delegatedNodes--; }
    }
    dropTypeCount(type);
  }

  function dropTypes(node) {
    const l = node.__wybL;
    if (l === undefined) return;
    delete node.__wybL;
    delegatedNodes--;
    if (typeof l === "string") dropTypeCount(l);
    else for (const type of l) dropTypeCount(type);
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

  function listen(id, key, options = {}) {
    const type = key.endsWith(":capture") ? key.slice(0, -8) : key;
    const node = nodes.get(id);
    if (node === undefined) return;
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
      node.addEventListener(type, fn, options);
      return;
    }
    addType(node, type);
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
    const node = nodes.get(id);
    if (node !== undefined) removeType(node, key);
  }

  // -- release ------------------------------------------------------------

  function releaseId(id) {
    const node = nodes.get(id);
    if (node === undefined) return;
    controlledSelects.delete(id);
    const entries = directListeners.get(id);
    if (entries) {
      for (const entry of entries.values()) node.removeEventListener(entry.type, entry.fn, entry.options);
      directListeners.delete(id);
    }
    dropTypes(node);
    if (node.__wybId === id) delete node.__wybId;
    nodes.delete(id);
  }

  // Release every registered node in the subtree rooted at `root`. Removed
  // DOM is final, so the kernel finds the ids natively instead of Python
  // sending one per node.
  function releaseTree(root) {
    let n = root;
    while (n) {
      const id = n.__wybId;
      if (id !== undefined && nodes.get(id) === n) releaseId(id);
      if (n.firstChild) n = n.firstChild;
      else {
        while (n !== root && !n.nextSibling) n = n.parentNode;
        if (n === root) break;
        n = n.nextSibling;
      }
    }
  }

  function disposeRange(first, last) {
    if (!first || !last) return;
    const after = last.nextSibling;
    const parent = first.parentNode;
    let current = first;
    while (current && current !== after) {
      const next = current.nextSibling;
      releaseTree(current);
      current = next;
    }
    if (first !== last && parent !== null && parent === last.parentNode) {
      // One native range deletion instead of a removal per node.
      const range = doc.createRange();
      range.setStartBefore(first);
      range.setEndAfter(last);
      range.deleteContents();
      return;
    }
    current = first;
    while (current && current !== after) {
      const next = current.nextSibling;
      if (current.parentNode) current.parentNode.removeChild(current);
      current = next;
    }
  }

  // -- templates ----------------------------------------------------------

  function registerTpl(tplId, html, count, texts, listens) {
    const tpl = doc.createElement("template");
    tpl.innerHTML = html;
    const proto = tpl.content.firstChild;
    proto.remove();
    templates.set(tplId, {proto, count, texts: texts || [], listens: listens || []});
  }

  // Clone a template, register its nodes as a dense pre-order id block,
  // fill its text slots, mark its delegated listeners, and insert it.
  // The pre-order must match the order the Python shape walk counts nodes
  // in (element, then children left to right).
  function clone(op) {
    const first = op[1];
    const t = templates.get(op[2]);
    const root = t.proto.cloneNode(true);
    const texts = t.texts;
    const listens = t.listens;
    let slot = 0;
    let nextText = texts.length ? texts[0] : -1;
    let id = first;
    let n = root;
    while (n) {
      nodes.set(id, n);
      n.__wybId = id;
      if (id - first === nextText) {
        n.nodeValue = op[5 + slot];
        slot++;
        nextText = slot < texts.length ? texts[slot] : -1;
      }
      id++;
      if (n.firstChild) n = n.firstChild;
      else {
        while (n !== root && !n.nextSibling) n = n.parentNode;
        if (n === root) break;
        n = n.nextSibling;
      }
    }
    if (id - first !== t.count) {
      throw new Error(`wybthon kernel: template node count mismatch (expected ${t.count}, got ${id - first})`);
    }
    for (let i = 0; i < listens.length; i++) {
      const entry = listens[i];
      addType(nodes.get(first + entry[0]), entry[1]);
    }
    insert(op[3], root, op[4]);
  }

  function insert(parentId, node, anchorId) {
    // The anchor's live parent wins over the parent id: a subtree parked
    // off-document by a Loading boundary keeps receiving updates
    // addressed to its original parent.
    const anchor = anchorId === null ? undefined : nodes.get(anchorId);
    if (hydrating !== null) hydrating.fresh.add(node);
    if (anchor !== undefined && anchor.parentNode !== null) {
      anchor.parentNode.insertBefore(node, anchor);
    } else {
      nodes.get(parentId).appendChild(node);
    }
  }

  // -- hydration ----------------------------------------------------------
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
  // Keep a server region the client won't hydrate (`NoHydration`) as static
  // DOM: advance the parent's cursor to its end marker, which is claimed next.
  function claimStatic(parentId, endData) {
    const parent = nodes.get(parentId);
    let c = cursorOf(parent);
    while (c) {
      if (c.nodeType === 8 && c.nodeValue === endData) {
        hydrating.cursors.set(parent, c);
        return;
      }
      hydrating.fresh.add(c);
      c = c.nextSibling;
    }
    hydrating.cursors.set(parent, null);
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

  // -- dispatch -----------------------------------------------------------

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
        if (id !== undefined && hasType(node, type)) route.push([id, type]);
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

  // -- command interpreter --------------------------------------------------

  function apply(opsJson) {
    const ops = JSON.parse(opsJson);
    for (let i = 0; i < ops.length; i++) {
      const op = ops[i];
      switch (op[0]) {
        case 1: // CREATE_ELEMENT
          reg(op[1], doc.createElement(op[2]));
          break;
        case 2: // CREATE_TEXT
          reg(op[1], doc.createTextNode(op[2]));
          break;
        case 3: // CREATE_COMMENT
          reg(op[1], doc.createComment(op[2] || ""));
          break;
        case 4: // CLONE
          clone(op);
          break;
        case 5: // INSERT
          insert(op[1], nodes.get(op[2]), op[3]);
          break;
        case 6: { // REMOVE
          const n = nodes.get(op[1]);
          if (n !== undefined && n.parentNode !== null) n.parentNode.removeChild(n);
          break;
        }
        case 7: // SET_TEXT
          nodes.get(op[1]).nodeValue = op[2];
          break;
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
        case 11: // LISTEN
          listen(op[1], op[2], op[3]);
          break;
        case 12: // UNLISTEN
          unlisten(op[1], op[2]);
          break;
        case 13: { // RELEASE
          const ids = op[1];
          for (let k = 0; k < ids.length; k++) releaseId(ids[k]);
          break;
        }
        case 14: // REGISTER_TPL
          registerTpl(op[1], op[2], op[3], op[4], op[5]);
          break;
        case 15: // CREATE_ELEMENT_NS
          reg(op[1], doc.createElementNS(op[2], op[3]));
          break;
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
        case 19: // DISPOSE_RANGE
          disposeRange(nodes.get(op[1]), nodes.get(op[2]));
          break;
        case 20: // RELEASE_TPL
          templates.delete(op[1]);
          break;
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
        case 22: // HYDRATE
          hydrating = {
            root: nodes.get(op[1]), cursors: new Map(), touched: new Set(), fresh: new Set(), mismatches: 0,
          };
          break;
        case 23: // CLAIM_ELEMENT
          claimElement(op[1], op[2], op[3], op[4]);
          break;
        case 24: // CLAIM_TEXT
          claimText(op[1], op[2], op[3]);
          break;
        case 25: // CLAIM_COMMENT
          claimComment(op[1], op[2], op[3]);
          break;
        case 26: // HYDRATE_END
          if (hydrating !== null) endHydration();
          break;
        case 27: { // DISPOSE
          const n = nodes.get(op[1]);
          if (n !== undefined) {
            releaseTree(n);
            if (n.parentNode) n.parentNode.removeChild(n);
          }
          break;
        }
        case 28: // CLAIM_STATIC
          if (hydrating !== null) claimStatic(op[1], op[2]);
          break;
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
      listeners: delegatedNodes + directListeners.size,
      roots: roots.size,
      types: typeCounts.size,
      templates: templates.size,
      hydration_mismatches: hydrationMismatches,
    }),
  };
})()
