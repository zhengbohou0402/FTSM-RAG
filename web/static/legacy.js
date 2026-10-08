const $ = (id) => document.getElementById(id);

async function requestJson(path) {
  const res = await fetch(path);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText || "Request failed");
  return data;
}

function setText(id, value) {
  $(id).textContent = value === null || value === undefined || value === "" ? "-" : String(value);
}

function setStatus(id, ok, text) {
  const el = $(id);
  el.textContent = text || (ok ? "OK" : "Error");
  el.classList.toggle("legacy-ok", Boolean(ok));
  el.classList.toggle("legacy-error", !ok);
}

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatBool(value) {
  return value ? "Yes" : "No";
}

function formatRate(value) {
  return typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "-";
}

function setOverall(ok, message) {
  const box = $("legacy-overall");
  const dot = box.querySelector(".legacy-dot");
  box.classList.toggle("legacy-banner-ok", ok);
  box.classList.toggle("legacy-banner-error", !ok);
  dot.className = `legacy-dot ${ok ? "legacy-dot-ok" : "legacy-dot-error"}`;
  box.querySelector("span:last-child").textContent = message;
}

async function loadStatus() {
  const refreshBtn = $("legacy-refresh");
  refreshBtn.disabled = true;
  setOverall(true, "Checking backend...");

  try {
    const [health, config, kb, cache, training, scheduler] = await Promise.all([
      requestJson("/api/health"),
      requestJson("/api/config/status"),
      requestJson("/api/knowledge/stats"),
      requestJson("/api/cache/stats"),
      requestJson("/api/training/status"),
      requestJson("/api/scheduler/status"),
    ]);

    setStatus("legacy-api-status", true);
    setText("legacy-api-health", health.status || "ok");
    setText("legacy-api-key", config.dashscope_configured ? "Configured" : "Missing");

    setStatus("legacy-kb-status", true);
    setText("legacy-kb-docs", kb.document_count);
    setText("legacy-kb-chunks", kb.total_chunks);
    setText("legacy-kb-last", formatDate(kb.last_indexed));

    setStatus("legacy-cache-status", true);
    setText("legacy-cache-size", cache.size);
    setText("legacy-cache-rate", formatRate(cache.hit_rate));

    setStatus("legacy-training-status", !training.last_error, training.running ? "Running" : "Idle");
    setText("legacy-training-running", formatBool(training.running));
    setText("legacy-training-pending", formatBool(training.pending));
    setText("legacy-training-error", training.last_error || "-");

    setStatus(
      "legacy-scheduler-status",
      !scheduler.last_error,
      scheduler.running ? "Running" : scheduler.enabled ? "Enabled" : "Disabled",
    );
    setText("legacy-scheduler-enabled", formatBool(scheduler.enabled));
    setText("legacy-scheduler-thread", scheduler.thread_alive ? "Alive" : "Stopped");
    setText("legacy-scheduler-success", formatDate(scheduler.last_success || scheduler.last_run));
    setText("legacy-scheduler-next", formatDate(scheduler.next_run));
    setText("legacy-scheduler-error", scheduler.last_error || "-");

    const missingKey = !config.dashscope_configured;
    setOverall(!missingKey, missingKey ? "Backend is reachable, but DashScope API key is missing." : "Backend is reachable.");
  } catch (err) {
    setStatus("legacy-api-status", false);
    setOverall(false, err.message || "Backend check failed.");
  } finally {
    refreshBtn.disabled = false;
  }
}

$("legacy-refresh").addEventListener("click", loadStatus);
loadStatus();
