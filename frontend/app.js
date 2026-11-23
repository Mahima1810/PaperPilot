// PaperPilot front end. Plain ES modules, no build step.
// All text that comes from PDFs or the model is inserted with textContent, never innerHTML.

const $ = (id) => document.getElementById(id);
const els = {
  dropzone: $("dropzone"), fileInput: $("file-input"), library: $("library"), docCount: $("doc-count"),
  status: $("status"), statusText: $("status-text"), docTitle: $("doc-title"), docMeta: $("doc-meta"),
  messages: $("messages"), empty: $("empty"), suggestions: $("suggestions"), composer: $("composer"),
  question: $("question"), askBtn: $("ask-btn"), source: $("source"), sourceTitle: $("source-title"),
  sourceText: $("source-text"), sourceClose: $("source-close"), toast: $("toast"),
  sectionsBar: $("sections-bar"), toggleSections: $("toggle-sections"),
};

const SUGGESTIONS = [
  "What problem does this paper solve?",
  "What datasets were used?",
  "What are the main results?",
  "What are the limitations?",
];

const ICONS = {
  bot: '<svg viewBox="0 0 24 24"><path d="M9 18 18 7M12 7h6v6"/></svg>',
  trash: '<svg viewBox="0 0 24 24"><path d="M4 7h16M10 11v6m4-6v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/></svg>',
};

const state = { docs: [], activeId: null, busy: false, history: new Map() };

// ---------- helpers ----------
function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) if (c) node.append(c);
  return node;
}

function toast(message, isError = false) {
  els.toast.textContent = message;
  els.toast.className = `toast${isError ? " error" : ""}`;
  els.toast.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (els.toast.hidden = true), 4000);
}

async function api(path, options = {}) {
  const res = await fetch(path, options);
  if (res.status === 204) return null;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail?.[0]?.msg || body.detail || `Request failed (${res.status})`);
  return body;
}

const pages = (c) => (c.page_start === c.page_end ? `p. ${c.page_start}` : `pp. ${c.page_start}–${c.page_end}`);

// ---------- status ----------
async function loadHealth() {
  try {
    const h = await api("/api/health");
    els.status.className = "status ok";
    els.statusText.textContent = h.mode === "llm" ? `LLM mode · ${h.model}` : "Extractive mode · offline";
  } catch {
    els.status.className = "status err";
    els.statusText.textContent = "Server unreachable";
  }
}

// ---------- library ----------
async function loadDocs(selectId) {
  state.docs = await api("/api/documents");
  els.docCount.textContent = state.docs.length;
  renderLibrary();
  const next = selectId || state.activeId || state.docs[0]?.id;
  selectDoc(state.docs.some((d) => d.id === next) ? next : state.docs[0]?.id ?? null);
}

function renderLibrary() {
  els.library.replaceChildren(
    ...state.docs.map((d) =>
      el("li", { class: d.id === state.activeId ? "active" : "", title: d.title, onclick: () => selectDoc(d.id) }, [
        el("span", { class: "lib-title", text: d.title }),
        el("span", { class: "lib-meta", text: `${d.num_pages} pages · ${d.filename}` }),
        (() => {
          const b = el("button", { class: "lib-del", "aria-label": `Remove ${d.title}`, onclick: (e) => { e.stopPropagation(); removeDoc(d); } });
          b.innerHTML = ICONS.trash; // static icon markup only
          return b;
        })(),
      ]),
    ),
  );
}

function selectDoc(id) {
  state.activeId = id;
  const doc = state.docs.find((d) => d.id === id);
  renderLibrary();
  closeSource();
  els.question.disabled = els.askBtn.disabled = !doc;
  els.toggleSections.hidden = !doc;
  els.sectionsBar.hidden = true;
  if (!doc) {
    els.docTitle.textContent = "Upload a paper to start";
    els.docMeta.textContent = "No paper selected";
    renderMessages([]);
    return;
  }
  els.docTitle.textContent = doc.title;
  els.docMeta.textContent = `${doc.num_pages} pages · ${doc.sections.length} sections · ${doc.num_chunks} passages`;
  els.sectionsBar.replaceChildren(...doc.sections.map((s) => el("span", { text: s })));
  renderMessages(state.history.get(id) || []);
  els.question.focus();
}

async function removeDoc(doc) {
  if (!confirm(`Remove "${doc.title}" from your library?`)) return;
  try {
    await api(`/api/documents/${doc.id}`, { method: "DELETE" });
    state.history.delete(doc.id);
    if (state.activeId === doc.id) state.activeId = null;
    await loadDocs();
    toast("Paper removed");
  } catch (e) {
    toast(e.message, true);
  }
}

// ---------- upload ----------
async function upload(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".pdf")) return toast("Please choose a PDF file.", true);
  const form = new FormData();
  form.append("file", file);
  els.dropzone.classList.add("busy");
  els.dropzone.querySelector(".dz-title").textContent = "Reading paper…";
  try {
    const doc = await api("/api/documents", { method: "POST", body: form });
    await loadDocs(doc.id);
    toast(doc.created ? `Indexed ${doc.num_chunks} passages from ${doc.num_pages} pages` : "Already in your library");
  } catch (e) {
    toast(e.message, true);
  } finally {
    els.dropzone.classList.remove("busy");
    els.dropzone.querySelector(".dz-title").textContent = "Drop a PDF here";
    els.fileInput.value = "";
  }
}

els.fileInput.addEventListener("change", () => upload(els.fileInput.files[0]));
els.dropzone.addEventListener("keydown", (e) => (e.key === "Enter" || e.key === " ") && els.fileInput.click());
["dragenter", "dragover"].forEach((t) =>
  els.dropzone.addEventListener(t, (e) => { e.preventDefault(); els.dropzone.classList.add("drag"); }),
);
["dragleave", "drop"].forEach((t) =>
  els.dropzone.addEventListener(t, (e) => { e.preventDefault(); els.dropzone.classList.remove("drag"); }),
);
els.dropzone.addEventListener("drop", (e) => upload(e.dataTransfer.files[0]));

// ---------- chat ----------
function renderMessages(items) {
  els.messages.replaceChildren();
  if (!items.length) {
    els.suggestions.replaceChildren(
      ...(state.activeId ? SUGGESTIONS : []).map((q) => el("button", { type: "button", text: q, onclick: () => ask(q) })),
    );
    els.messages.append(els.empty);
    return;
  }
  items.forEach((m) => els.messages.append(m.role === "user" ? userBubble(m.text) : botBubble(m.data)));
  els.messages.scrollTop = els.messages.scrollHeight;
}

const userBubble = (text) => el("div", { class: "msg user" }, el("div", { class: "bubble", text }));

function avatar() {
  const a = el("div", { class: "avatar" });
  a.innerHTML = ICONS.bot;
  return a;
}

function botBubble(data) {
  const byN = new Map(data.citations.map((c) => [c.n, c]));
  const p = el("p", { class: "answer-text" });
  // Split the answer on citation markers like [1] or [1, 3] and turn them into buttons.
  data.answer.split(/(\[\d+(?:\s*,\s*\d+)*\])/g).forEach((part) => {
    const m = part.match(/^\[([\d,\s]+)\]$/);
    if (!m) return p.append(document.createTextNode(part));
    m[1].split(",").map((s) => Number(s.trim())).forEach((n) => {
      const c = byN.get(n);
      if (c) p.append(el("button", { class: "cite", type: "button", title: `${c.section} · ${pages(c)}`, text: String(n), onclick: (e) => openSource(c, e.currentTarget) }));
    });
  });

  const label = { llm: "Generated · cited", extractive: "Quoted from paper", not_found: "Not in paper" }[data.mode] || data.mode;
  const meta = el("div", { class: "meta-row" }, [
    el("span", { class: `badge ${data.mode}`, text: label }),
    ...data.citations.map((c) =>
      el("button", { class: "src-chip", type: "button", text: `[${c.n}] ${c.section} · ${pages(c)}`, onclick: (e) => openSource(c, e.currentTarget) }),
    ),
  ]);
  const bubble = el("div", { class: "bubble" }, [p, meta, data.warning && el("p", { class: "warning", text: data.warning })]);
  return el("div", { class: "msg bot" }, [avatar(), bubble]);
}

function typingBubble() {
  return el("div", { class: "msg bot" }, [avatar(), el("div", { class: "bubble typing" }, [el("span"), el("span"), el("span")])]);
}

async function ask(question) {
  question = question.trim();
  if (!question || state.busy || !state.activeId) return;
  if (question.length < 3) return toast("Please ask a longer question.", true);
  const id = state.activeId;
  const history = state.history.get(id) || [];
  history.push({ role: "user", text: question });
  state.history.set(id, history);
  renderMessages(history);
  const typing = typingBubble();
  els.messages.append(typing);
  els.messages.scrollTop = els.messages.scrollHeight;
  els.question.value = "";
  state.busy = true;
  els.askBtn.disabled = true;
  try {
    const data = await api(`/api/documents/${id}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    history.push({ role: "bot", data });
  } catch (e) {
    history.push({ role: "bot", data: { answer: `Something went wrong: ${e.message}`, mode: "not_found", citations: [] } });
  } finally {
    state.busy = false;
    els.askBtn.disabled = false;
    if (state.activeId === id) renderMessages(history);
    els.question.focus();
  }
}

els.composer.addEventListener("submit", (e) => { e.preventDefault(); ask(els.question.value); });

// ---------- source panel ----------
function openSource(c, trigger) {
  document.querySelectorAll(".cite.active").forEach((b) => b.classList.remove("active"));
  if (trigger?.classList.contains("cite")) trigger.classList.add("active");
  els.sourceTitle.textContent = `[${c.n}] ${c.section} · ${pages(c)}`;
  els.sourceText.textContent = c.quote;
  els.source.hidden = false;
}
function closeSource() {
  els.source.hidden = true;
  document.querySelectorAll(".cite.active").forEach((b) => b.classList.remove("active"));
}
els.sourceClose.addEventListener("click", closeSource);
document.addEventListener("keydown", (e) => e.key === "Escape" && closeSource());
els.toggleSections.addEventListener("click", () => (els.sectionsBar.hidden = !els.sectionsBar.hidden));

// ---------- start ----------
loadHealth();
loadDocs().catch((e) => toast(e.message, true));
