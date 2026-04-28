const fileInput  = document.getElementById("manage-file-input");
const browseBtn  = document.getElementById("manage-browse");
const dropzone   = document.getElementById("manage-dropzone");
const resultBox  = document.getElementById("manage-result");
const docCount   = document.getElementById("manage-doc-count");
const docList    = document.getElementById("manage-doc-list");
const reindexBtn = document.getElementById("manage-reindex");
const refreshBtn = document.getElementById("manage-refresh");

function setResult(html) { resultBox.innerHTML = html || ""; }

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value ?? "";
  return div.innerHTML;
}

async function requestJson(url, options = {}) {
  const res  = await fetch(url, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Request failed");
  return data;
}

// ── Relative time ─────────────────────────────────────────────────────────────

function formatRelativeTime(iso) {
  if (!iso) return null;
  const diff = (Date.now() - new Date(iso)) / 1000;
  if (diff < 60)   return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

// ── Stats ─────────────────────────────────────────────────────────────────────

async function loadStats() {
  try {
    const [kb, cache] = await Promise.all([
      requestJson("/api/knowledge/stats"),
      requestJson("/api/cache/stats"),
    ]);

    document.getElementById("stats-section").style.display = "";

    // KB stats
    document.getElementById("kbs-docs").textContent    = kb.document_count ?? "—";
    document.getElementById("kbs-chunks").textContent  = kb.total_chunks ?? "—";
    document.getElementById("kbs-records").textContent = kb.manifest_records ?? "—";

    const relTime = formatRelativeTime(kb.last_indexed);
    document.getElementById("kbs-last").textContent    = relTime || "—";
    document.getElementById("kbs-last-sub").textContent =
      kb.last_indexed ? new Date(kb.last_indexed).toLocaleString() : "";

    // Cache stats
    const hitRate = typeof cache.hit_rate === "number"
      ? `${(cache.hit_rate * 100).toFixed(1)}%` : "—";
    document.getElementById("cache-rate").textContent    = hitRate;
    document.getElementById("cache-hits").textContent    = cache.hit_count  ?? "—";
    document.getElementById("cache-misses").textContent  = cache.miss_count ?? "—";
    document.getElementById("cache-size").textContent    = cache.size       ?? "—";
    document.getElementById("cache-valid-sub").textContent =
      typeof cache.valid === "number" ? `${cache.valid} valid` : "";
  } catch {}
}

// ── Indexing status polling ───────────────────────────────────────────────────

let _pollTimer = null;

function stopPoll() {
  if (_pollTimer) { clearTimeout(_pollTimer); _pollTimer = null; }
}

async function pollTrainingStatus() {
  const bar  = document.getElementById("index-status-bar");
  const dot  = document.getElementById("index-status-dot");
  const text = document.getElementById("index-status-text");
  const errEl = document.getElementById("index-status-error");

  try {
    const data = await requestJson("/api/training/status");
    bar.style.display = "";

    dot.className = "index-status-dot";
    errEl.textContent = "";

    if (data.running) {
      dot.classList.add("dot-running");
      text.textContent = "Indexing in progress…";
      _pollTimer = setTimeout(pollTrainingStatus, 2000);
    } else if (data.pending) {
      dot.classList.add("dot-running");
      text.textContent = "Indexing queued…";
      _pollTimer = setTimeout(pollTrainingStatus, 2000);
    } else if (data.last_result === "success") {
      dot.classList.add("dot-ok");
      text.textContent = "Indexing complete";
      loadStats();
    } else if (data.last_error) {
      dot.classList.add("dot-fail");
      text.textContent = "Indexing failed";
      errEl.textContent = data.last_error;
    } else {
      dot.classList.add("dot-ok");
      text.textContent = "Index up to date";
    }
  } catch {}
}

function startPoll() {
  stopPoll();
  pollTrainingStatus();
}

// ── Document list ─────────────────────────────────────────────────────────────

async function loadDocuments() {
  try {
    const data = await requestJson("/api/documents");
    const docs = data.documents || [];
    docCount.textContent = `${docs.length} files`;
    if (!docs.length) {
      docList.innerHTML = '<div class="manage-empty">No documents yet.</div>';
      return;
    }
    docList.innerHTML = docs
      .map(
        (doc) => `
        <div class="manage-item">
          <div>
            <div class="manage-name">${escapeHtml(doc.name)}</div>
            <div class="manage-meta">${Math.round(doc.size / 1024)} KB</div>
          </div>
          <button class="manage-delete" data-name="${escapeHtml(doc.name)}">Delete</button>
        </div>`,
      )
      .join("");
    docList.querySelectorAll(".manage-delete").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!confirm(`Delete ${btn.dataset.name}?`)) return;
        try {
          const data = await requestJson(
            `/api/documents/${encodeURIComponent(btn.dataset.name)}`,
            { method: "DELETE" },
          );
          const chunks  = Number(data.deleted_chunks || 0);
          const suffix  = data.manifest_found ? ` and removed ${chunks} vector chunks` : "";
          setResult(`<div class="manage-ok">Deleted ${escapeHtml(btn.dataset.name)}${suffix}</div>`);
          loadDocuments();
          loadStats();
        } catch (err) {
          setResult(`<div class="manage-err">${escapeHtml(err.message)}</div>`);
        }
      });
    });
  } catch (err) {
    setResult(`<div class="manage-err">${escapeHtml(err.message)}</div>`);
  }
}

// ── Upload ────────────────────────────────────────────────────────────────────

async function uploadFiles(files) {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  try {
    const res  = await fetch("/api/upload", { method: "POST", body: formData });
    const data = await res.json();
    const lines = [];
    if (data.saved?.length)
      lines.push(`<div class="manage-ok">Saved: ${data.saved.map(escapeHtml).join(", ")}</div>`);
    if (data.errors?.length)
      data.errors.forEach((e) =>
        lines.push(`<div class="manage-err">${escapeHtml(e.name)}: ${escapeHtml(e.error)}</div>`),
      );
    if (data.training_started) {
      lines.push('<div class="manage-ok">Indexing started…</div>');
      startPoll();
    }
    setResult(lines.join(""));
    loadDocuments();
  } catch (err) {
    setResult(`<div class="manage-err">${escapeHtml(err.message)}</div>`);
  }
}

// ── Events ────────────────────────────────────────────────────────────────────

browseBtn.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("click",  () => fileInput.click());
fileInput.addEventListener("change", () => {
  if (fileInput.files.length) uploadFiles(Array.from(fileInput.files));
});
dropzone.addEventListener("dragover", (e) => {
  e.preventDefault(); dropzone.classList.add("drag");
});
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("drag"));
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("drag");
  const files = Array.from(e.dataTransfer.files);
  if (files.length) uploadFiles(files);
});
reindexBtn.addEventListener("click", async () => {
  try {
    const data = await requestJson("/api/training/start", { method: "POST" });
    setResult(`<div class="manage-ok">${escapeHtml(data.message)}</div>`);
    startPoll();
  } catch (err) {
    setResult(`<div class="manage-err">${escapeHtml(err.message)}</div>`);
  }
});
refreshBtn.addEventListener("click", () => {
  loadDocuments();
  loadStats();
  startPoll();
});

// ── Init ──────────────────────────────────────────────────────────────────────

loadDocuments();
loadStats();
startPoll();
