const fileInput = document.getElementById("manage-file-input");
const browseBtn = document.getElementById("manage-browse");
const dropzone = document.getElementById("manage-dropzone");
const resultBox = document.getElementById("manage-result");
const docCount = document.getElementById("manage-doc-count");
const docList = document.getElementById("manage-doc-list");
const reindexBtn = document.getElementById("manage-reindex");
const refreshBtn = document.getElementById("manage-refresh");

function setResult(html) {
  resultBox.innerHTML = html || "";
}

async function requestJson(url, options = {}) {
  const res = await fetch(url, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Request failed");
  return data;
}

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
            <div class="manage-name">${doc.name}</div>
            <div class="manage-meta">${Math.round(doc.size / 1024)} KB</div>
          </div>
          <button class="manage-delete" data-name="${doc.name}">Delete</button>
        </div>`,
      )
      .join("");
    docList.querySelectorAll(".manage-delete").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!confirm(`Delete ${btn.dataset.name}?`)) return;
        try {
          await requestJson(`/api/documents/${encodeURIComponent(btn.dataset.name)}`, {
            method: "DELETE",
          });
          setResult(`<div class="manage-ok">Deleted ${btn.dataset.name}</div>`);
          loadDocuments();
        } catch (err) {
          setResult(`<div class="manage-err">${err.message}</div>`);
        }
      });
    });
  } catch (err) {
    setResult(`<div class="manage-err">${err.message}</div>`);
  }
}

async function uploadFiles(files) {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  try {
    const res = await fetch("/api/upload", { method: "POST", body: formData });
    const data = await res.json();
    const lines = [];
    if (data.saved?.length) lines.push(`<div class="manage-ok">Saved: ${data.saved.join(", ")}</div>`);
    if (data.errors?.length) {
      data.errors.forEach((err) => lines.push(`<div class="manage-err">${err.name}: ${err.error}</div>`));
    }
    if (data.training_started) lines.push('<div class="manage-ok">Indexing started</div>');
    setResult(lines.join(""));
    loadDocuments();
  } catch (err) {
    setResult(`<div class="manage-err">${err.message}</div>`);
  }
}

browseBtn.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => {
  if (fileInput.files.length) uploadFiles(Array.from(fileInput.files));
});
dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropzone.classList.add("drag");
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
    setResult(`<div class="manage-ok">${data.message}</div>`);
  } catch (err) {
    setResult(`<div class="manage-err">${err.message}</div>`);
  }
});
refreshBtn.addEventListener("click", loadDocuments);

loadDocuments();
