const chatForm = document.getElementById("chat-form");
const messageInput = document.getElementById("message-input");
const sendBtn = document.getElementById("send-btn");
const chatLog = document.getElementById("chat-log");
const welcome = document.getElementById("welcome");
const historyList = document.getElementById("history-list");
const sidebar = document.getElementById("sidebar");
const authScreen = document.getElementById("auth-screen");
const authForm = document.getElementById("auth-form");
const authStudentId = document.getElementById("auth-student-id");
const authPassword = document.getElementById("auth-password");
const authDisplayName = document.getElementById("auth-display-name");
const authSubmit = document.getElementById("auth-submit");
const authSwitch = document.getElementById("auth-switch");
const authError = document.getElementById("auth-error");
const logoutBtn = document.getElementById("logout-btn");
const topbarUser = document.getElementById("topbar-user");
const STORAGE_KEY = "ukm_ftsm_chat_v3";
const THEME_KEY = "ukm_ftsm_theme";
const MAX_HISTORY = 20;

let chatHistory = [];
let conversationId = null;
let busy = false;
let currentStudent = null;
let authMode = "login";

// ── Theme Management ──

function initTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
  }
}

function toggleTheme() {
  const isDark = document.documentElement.getAttribute("data-theme") === "dark";
  if (isDark) {
    document.documentElement.removeAttribute("data-theme");
    localStorage.setItem(THEME_KEY, "light");
  } else {
    document.documentElement.setAttribute("data-theme", "dark");
    localStorage.setItem(THEME_KEY, "dark");
  }
}

document.getElementById("theme-toggle").addEventListener("click", toggleTheme);
initTheme();

// ── Helpers ──

function scrollToBottom() {
  chatLog.scrollTop = chatLog.scrollHeight;
}

function autoResize() {
  messageInput.style.height = "auto";
  messageInput.style.height = Math.min(messageInput.scrollHeight, 200) + "px";
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function renderMd(text) {
  if (!text) return "";
  if (window.marked) {
    window.marked.setOptions({ breaks: true, gfm: true });
    const html = window.marked.parse(text);
    return window.DOMPurify ? window.DOMPurify.sanitize(html) : html;
  }
  return escapeHtml(text).replace(/\n/g, "<br>");
}

function summarize(text) {
  const c = text.replace(/\s+/g, " ").trim();
  return c.length > 36 ? c.slice(0, 36) + "..." : c || "New chat";
}

function showToast(message) {
  const existing = document.querySelector(".toast");
  if (existing) existing.remove();

  const toast = document.createElement("div");
  toast.className = "toast";
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 2000);
}

// Auth

function getStorageKey() {
  return currentStudent
    ? `${STORAGE_KEY}:${currentStudent.student_id}`
    : STORAGE_KEY;
}

function setAuthError(message) {
  authError.textContent = message || "";
}

function setAuthMode(mode) {
  authMode = mode;
  const isRegister = mode === "register";
  authScreen.classList.toggle("registering", isRegister);
  authSubmit.textContent = isRegister ? "Create account" : "Sign in";
  authSwitch.textContent = isRegister
    ? "I already have an account"
    : "Create a student account";
  authPassword.autocomplete = isRegister ? "new-password" : "current-password";
  setAuthError("");
}

function setAuthenticated(student) {
  currentStudent = student;
  topbarUser.textContent = student.display_name || student.student_id;
  document.body.classList.remove("auth-locked");
  authScreen.classList.add("hidden");
  chatHistory = loadHistory();
  renderHistory();
  syncServerHistory();
  messageInput.focus();
}

async function fetchJson(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Request failed.");
  return data;
}

async function initAuth() {
  try {
    const data = await fetchJson("/api/auth/me");
    if (data.student) {
      setAuthenticated(data.student);
      return;
    }
  } catch {}
  authScreen.classList.remove("hidden");
  setAuthMode("login");
  authStudentId.focus();
}

authSwitch.addEventListener("click", () => {
  setAuthMode(authMode === "login" ? "register" : "login");
});

authForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  authSubmit.disabled = true;
  setAuthError("");
  try {
    const payload = {
      student_id: authStudentId.value,
      password: authPassword.value,
      display_name: authDisplayName.value,
    };
    const endpoint =
      authMode === "register" ? "/api/auth/register" : "/api/auth/login";
    const data = await fetchJson(endpoint, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (data.student) setAuthenticated(data.student);
  } catch (err) {
    setAuthError(err.message);
  } finally {
    authSubmit.disabled = false;
  }
});

logoutBtn.addEventListener("click", async () => {
  try {
    await fetchJson("/api/auth/logout", { method: "POST" });
  } catch {}
  currentStudent = null;
  document.body.classList.add("auth-locked");
  conversationId = null;
  chatHistory = [];
  renderHistory();
  newChat();
  topbarUser.textContent = "";
  authScreen.classList.remove("hidden");
  setAuthMode("login");
  authPassword.value = "";
  authStudentId.focus();
});

// ── Sidebar History ──

function loadHistory() {
  try {
    const raw = localStorage.getItem(getStorageKey());
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveHistory() {
  localStorage.setItem(getStorageKey(), JSON.stringify(chatHistory));
}

function renderHistory() {
  historyList.innerHTML = "";
  chatHistory.forEach((c) => {
    const item = document.createElement("div");
    item.className = "history-item-wrap";

    const btn = document.createElement("button");
    btn.className = "history-item";
    btn.textContent = c.title;
    btn.dataset.id = c.id;

    const deleteBtn = document.createElement("button");
    deleteBtn.className = "history-delete-btn";
    deleteBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>`;
    deleteBtn.dataset.id = c.id;
    deleteBtn.title = "Delete";

    item.appendChild(btn);
    item.appendChild(deleteBtn);
    historyList.appendChild(item);
  });
}

function deleteConversation(id) {
  chatHistory = chatHistory.filter((c) => c.id !== id);
  saveHistory();
  renderHistory();
}

function upsertConversation() {
  const msgs = [];
  chatLog.querySelectorAll(".msg").forEach((el) => {
    const bubble = el.querySelector(".bubble");
    if (!bubble) return;
    if (el.classList.contains("msg-user")) {
      msgs.push({ role: "user", text: bubble.textContent.trim() });
    } else if (el.classList.contains("msg-assistant")) {
      msgs.push({ role: "assistant", text: bubble.textContent.trim() });
    }
  });
  if (!msgs.length) return;

  const first = msgs.find((m) => m.role === "user");
  const title = summarize(first ? first.text : "New chat");
  const id = conversationId || Date.now().toString();
  conversationId = id;

  chatHistory = chatHistory.filter((c) => c.id !== id);
  chatHistory.unshift({ id, title, msgs, ts: Date.now() });
  chatHistory = chatHistory.slice(0, MAX_HISTORY);
  saveHistory();
  renderHistory();
}

function loadConversation(conv) {
  chatLog.innerHTML = "";
  if (welcome) welcome.remove();
  conv.msgs.forEach((m) => createMsg(m.role, m.text));
  conversationId = conv.id;
  scrollToBottom();
}

// ── Messages ──

function createMsg(role, text) {
  if (welcome && welcome.parentNode) welcome.remove();

  const div = document.createElement("div");
  div.className = `msg msg-${role}`;

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  if (role === "assistant") {
    bubble.innerHTML = text ? renderMd(text) : "";

    // Add action buttons (copy)
    const actions = document.createElement("div");
    actions.className = "msg-actions";

    const copyBtn = document.createElement("button");
    copyBtn.className = "msg-action-btn";
    copyBtn.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="9" y="9" width="13" height="13" rx="2"/>
                <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
            </svg>
            Copy
        `;
    copyBtn.addEventListener("click", () => {
      navigator.clipboard.writeText(bubble.textContent).then(() => {
        showToast("Copied to clipboard");
      });
    });
    actions.appendChild(copyBtn);

    div.appendChild(bubble);
    div.appendChild(actions);
  } else {
    bubble.textContent = text;
    div.appendChild(bubble);
  }

  chatLog.appendChild(div);
  scrollToBottom();
  return bubble;
}

function showThinking(bubble) {
  bubble.innerHTML = `
        <div class="thinking">
            <div class="thinking-spinner"></div>
            <span class="thinking-text">Analyzing question...</span>
        </div>`;
}

function updateThinking(bubble, text) {
  const el = bubble.querySelector(".thinking-text");
  if (el) el.textContent = text;
}

function hideThinking(bubble) {
  const thinking = bubble.querySelector(".thinking");
  if (thinking) thinking.remove();
}

// ── Busy state ──

function setBusy(v) {
  busy = v;
  messageInput.disabled = v;
  sendBtn.disabled = v;
}

// ── Stream reply ──

async function streamReply(prompt) {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: prompt,
      conversation_id: conversationId,
      new_chat: false,
    }),
  });

  if (!res.ok || !res.body) {
    let msg = "Request failed.";
    try {
      const j = await res.json();
      msg = j.detail || msg;
    } catch {}
    throw new Error(msg);
  }

  const sid = res.headers.get("X-Conversation-Id");
  if (sid) conversationId = sid;
  return res.body.getReader();
}

async function send(prompt) {
  const p = prompt.trim();
  if (!p || busy) return;

  createMsg("user", p);
  const bubble = createMsg("assistant", "");
  setBusy(true);
  showThinking(bubble);

  try {
    const reader = await streamReply(p);
    const dec = new TextDecoder("utf-8");
    let buf = "";
    let result = "";
    let started = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buf += dec.decode(value, { stream: true });

      // Parse thinking markers
      while (buf.includes("__THINK__") && buf.includes("__ENDTHINK__")) {
        const si = buf.indexOf("__THINK__");
        const ei = buf.indexOf("__ENDTHINK__");
        if (si < ei) {
          result += buf.substring(0, si);
          const think = buf.substring(si + 9, ei).trim();
          buf = buf.substring(ei + 12);
          if (think) updateThinking(bubble, think);
        } else {
          break;
        }
      }

      if (buf && !buf.includes("__THINK__") && !buf.includes("__ENDTHINK__")) {
        result += buf;
        buf = "";
      }

      if (result.trim() && !started) {
        started = true;
        hideThinking(bubble);
        bubble.innerHTML = renderMd(result);
      } else if (started) {
        bubble.innerHTML = renderMd(result);
      }

      scrollToBottom();
    }

    if (buf) result += buf;
    bubble.innerHTML = renderMd(result.trim() || "No answer returned.");
    upsertConversation();

    // Re-add copy button after content update
    const parent = bubble.parentElement;
    if (parent && !parent.querySelector(".msg-actions")) {
      const actions = document.createElement("div");
      actions.className = "msg-actions";
      const copyBtn = document.createElement("button");
      copyBtn.className = "msg-action-btn";
      copyBtn.innerHTML = `
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="9" y="9" width="13" height="13" rx="2"/>
                    <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
                </svg>
                Copy
            `;
      copyBtn.addEventListener("click", () => {
        navigator.clipboard.writeText(bubble.textContent).then(() => {
          showToast("Copied to clipboard");
        });
      });
      actions.appendChild(copyBtn);
      parent.appendChild(actions);
    }
  } catch (err) {
    bubble.innerHTML = renderMd(`Error: ${err.message}`);
    upsertConversation();
  } finally {
    setBusy(false);
    messageInput.focus();
    scrollToBottom();
  }
}

// ── Events ──

chatForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const v = messageInput.value;
  messageInput.value = "";
  autoResize();
  send(v);
});

messageInput.addEventListener("input", autoResize);
messageInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    chatForm.requestSubmit();
  }
});

historyList.addEventListener("click", (e) => {
  // Delete button clicked
  const deleteBtn = e.target.closest(".history-delete-btn");
  if (deleteBtn) {
    e.stopPropagation();
    const id = deleteBtn.dataset.id;
    deleteConversation(id);
    return;
  }

  // History item clicked
  const btn = e.target.closest(".history-item");
  if (!btn) return;
  const conv = chatHistory.find((c) => c.id === btn.dataset.id);
  if (conv) loadConversation(conv);
  if (window.innerWidth <= 768) sidebar.classList.add("collapsed");
});

// Sidebar toggle
document.getElementById("sidebar-toggle").addEventListener("click", () => {
  sidebar.classList.toggle("collapsed");
});

// Suggestion cards
document.querySelectorAll(".suggestion-card").forEach((card) => {
  card.addEventListener("click", () => {
    const prompt = card.dataset.prompt;
    if (prompt) {
      messageInput.value = prompt;
      autoResize();
      chatForm.requestSubmit();
    }
  });
});

// New chat buttons
function newChat() {
  chatLog.innerHTML = `
        <div class="welcome" id="welcome">
            <div class="welcome-logo">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
                </svg>
            </div>
            <h1>How can I help you today?</h1>
            <div class="suggestion-grid">
                <button class="suggestion-card" data-prompt="Where can I view the academic calendar?">
                    <span class="suggestion-icon">📅</span>
                    <span class="suggestion-title">Academic Calendar</span>
                    <span class="suggestion-desc">Check semester dates and holidays</span>
                </button>
                <button class="suggestion-card" data-prompt="How do I check my course timetable?">
                    <span class="suggestion-icon">🗓️</span>
                    <span class="suggestion-title">Course Timetable</span>
                    <span class="suggestion-desc">View class schedules</span>
                </button>
                <button class="suggestion-card" data-prompt="What are the admission requirements for FTSM postgraduate programs?">
                    <span class="suggestion-icon">🎓</span>
                    <span class="suggestion-title">Admission Info</span>
                    <span class="suggestion-desc">Requirements and application process</span>
                </button>
                <button class="suggestion-card" data-prompt="How do I renew my student visa?">
                    <span class="suggestion-icon">📋</span>
                    <span class="suggestion-title">Visa Renewal</span>
                    <span class="suggestion-desc">Documents and procedures</span>
                </button>
            </div>
        </div>`;
  conversationId = null;
  messageInput.value = "";
  autoResize();
  messageInput.focus();

  // Re-bind suggestion card events
  document.querySelectorAll(".suggestion-card").forEach((card) => {
    card.addEventListener("click", () => {
      const prompt = card.dataset.prompt;
      if (prompt) {
        messageInput.value = prompt;
        autoResize();
        chatForm.requestSubmit();
      }
    });
  });
}

document.getElementById("new-chat-btn").addEventListener("click", newChat);
document.getElementById("new-chat-btn-top")?.addEventListener("click", newChat);

// ── Init ──
function syncServerHistory() {
  fetch("/api/conversations")
    .then((r) => {
      if (!r.ok) throw new Error("Could not load conversations.");
      return r.json();
    })
    .then((data) => {
      if (!Array.isArray(data.items)) return;
      const local = new Map(chatHistory.map((c) => [c.id, c]));
      data.items.forEach((item) => {
        if (local.has(item.id)) {
          local.get(item.id).title = item.title || local.get(item.id).title;
        }
      });
      renderHistory();
    })
    .catch(() => {});
}

autoResize();
initAuth();

