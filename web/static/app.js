const chatForm = document.getElementById("chat-form");
const messageInput = document.getElementById("message-input");
const sendBtn = document.getElementById("send-btn");
const chatLog = document.getElementById("chat-log");
const welcome = document.getElementById("welcome");
const historyList = document.getElementById("history-list");
const sidebar = document.getElementById("sidebar");

const THEME_KEY = "ukm_ftsm_theme";

const ICONS = {
  calendar: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="17" rx="2"></rect><path d="M8 2v4M16 2v4M3 10h18"></path></svg>',
  timetable: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="17" rx="2"></rect><path d="M8 2v4M16 2v4M8 14h3M13 14h3M8 18h3"></path></svg>',
  graduation: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 8l10-5 10 5-10 5-10-5z"></path><path d="M6 11v5c3 2 9 2 12 0v-5"></path></svg>',
  document: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3h7l4 4v14H7z"></path><path d="M14 3v5h5M9 13h6M9 17h6"></path></svg>',
  bus: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 4h12a2 2 0 0 1 2 2v9a3 3 0 0 1-3 3H7a3 3 0 0 1-3-3V6a2 2 0 0 1 2-2z"></path><path d="M4 10h16M8 18v2M16 18v2M8 14h.01M16 14h.01"></path></svg>',
  staff: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="4"></circle><path d="M4 21c1.5-4 14.5-4 16 0"></path></svg>',
  registration: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 4h14v16H5z"></path><path d="M8 8h8M8 12h8M8 16h5"></path></svg>',
  training: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 8h18v11H3z"></path><path d="M9 8V5h6v3M3 13h18"></path></svg>',
  facilities: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 21V8l8-5 8 5v13"></path><path d="M9 21v-7h6v7M8 10h.01M16 10h.01"></path></svg>',
  holiday: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h16"></path><path d="M6 20c0-5 3-9 6-9s6 4 6 9"></path><path d="M12 4v4M8 6l2 3M16 6l-2 3"></path></svg>',
  systems: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="13" rx="2"></rect><path d="M8 21h8M12 17v4"></path></svg>',
  exam: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h12v18H6z"></path><path d="M9 8h6M9 12h3M9 16h6"></path></svg>',
};
const SUGGESTIONS = [
  { icon: "calendar", title: "Academic Calendar", desc: "Check semester dates and holidays", prompt: "Where can I view the academic calendar?" },
  { icon: "timetable", title: "Course Timetable", desc: "View class schedules", prompt: "How do I check my course timetable?" },
  { icon: "graduation", title: "Admission Info", desc: "Requirements and application process", prompt: "What are the admission requirements for FTSM postgraduate programs?" },
  { icon: "document", title: "Visa Renewal", desc: "Documents and procedures", prompt: "How do I renew my student visa?" },
  { icon: "bus", title: "Campus Bus", desc: "Find routes and shuttle details", prompt: "How can I check UKM campus bus routes?" },
  { icon: "staff", title: "Staff Directory", desc: "Find lecturers and advisors", prompt: "How can I find FTSM academic staff and their expertise?" },
  { icon: "registration", title: "Registration", desc: "Understand renewal steps", prompt: "What should I prepare for course registration renewal?" },
  { icon: "training", title: "Industrial Training", desc: "Check contacts and guidance", prompt: "Where can I find industrial training information and contacts?" },
  { icon: "facilities", title: "Facilities", desc: "Ask about faculty services", prompt: "What facilities and services are available at FTSM?" },
  { icon: "holiday", title: "Public Holidays", desc: "Review Malaysia holiday dates", prompt: "What are the Malaysian public holidays for this academic year?" },
  { icon: "systems", title: "Student Systems", desc: "Find useful portals", prompt: "Which UKM student systems should I use for academic matters?" },
  { icon: "exam", title: "Exam Schedule", desc: "Ask about exam timing", prompt: "Where can I check my final exam schedule?" },
];

let conversationId = null;
let busy = false;

// Theme

function initTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === "dark") document.documentElement.setAttribute("data-theme", "dark");
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

// Helpers

function scrollToBottom() { chatLog.scrollTop = chatLog.scrollHeight; }

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

function pickSuggestions(count = 4) {
  const pool = [...SUGGESTIONS];
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [pool[i], pool[j]] = [pool[j], pool[i]];
  }
  return pool.slice(0, count);
}

function renderSuggestionCards() {
  return pickSuggestions()
    .map(
      (item) => `
        <button class="suggestion-card" data-prompt="${escapeHtml(item.prompt)}">
          <span class="suggestion-icon">${ICONS[item.icon] || ICONS.document}</span>
          <span class="suggestion-title">${escapeHtml(item.title)}</span>
          <span class="suggestion-desc">${escapeHtml(item.desc)}</span>
        </button>`,
    )
    .join("");
}

function bindSuggestionCards(root = document) {
  root.querySelectorAll(".suggestion-card").forEach((card) => {
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

function refreshWelcomeSuggestions() {
  const grid = document.querySelector(".suggestion-grid");
  if (!grid) return;
  grid.innerHTML = renderSuggestionCards();
  bindSuggestionCards(grid);
}

// Sidebar history — unified backend storage

function renderHistory(items) {
  historyList.innerHTML = "";
  (items || []).forEach((c) => {
    const item = document.createElement("div");
    item.className = "history-item-wrap";

    const btn = document.createElement("button");
    btn.className = "history-item";
    btn.textContent = c.title || "New chat";
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

async function fetchAndRenderHistory() {
  try {
    const res = await fetch("/api/conversations");
    if (!res.ok) return;
    const data = await res.json();
    renderHistory(data.items || []);
  } catch {}
}

async function deleteConversation(id) {
  try {
    await fetch(`/api/conversations/${id}`, { method: "DELETE" });
  } catch {}
  await fetchAndRenderHistory();
}

async function upsertConversation() {
  // 后端已在 stream_chat_answer 里 append_turn，只需刷新侧边栏
  await fetchAndRenderHistory();
}

async function loadConversation(id) {
  try {
    const res = await fetch(`/api/conversations/${id}`);
    if (!res.ok) return;
    const conv = await res.json();
    chatLog.innerHTML = "";
    const welcomeEl = document.getElementById("welcome");
    if (welcomeEl) welcomeEl.remove();
    (conv.messages || []).forEach((m) => createMsg(m.role, m.content));
    conversationId = conv.id;
    scrollToBottom();
  } catch {}
}

// ── Source cards ──────────────────────────────────────────────────────────────

/**
 * 把回复末尾 "Sources:\n- [N] name, chunk K: excerpt" 拆成折叠卡片。
 * 返回 { answerHtml, sourcesHtml }。
 */
function splitAnswerAndSources(rawText) {
  const match = rawText.match(/\n\nSources:\n([\s\S]+)$/);
  if (!match) return { answerHtml: renderMd(rawText.trim()), sourcesHtml: "" };

  const answerPart = rawText.slice(0, rawText.length - match[0].length).trim();
  const sourcesRaw = match[1];

  const lineRe = /^- \[(\d+)\] ([^:]+?)(?:, chunk (\d+))?: (.+)$/;
  const cards = sourcesRaw
    .split("\n")
    .filter((l) => l.startsWith("- ["))
    .map((line) => {
      const m = line.match(lineRe);
      if (!m) return null;
      return { num: m[1], name: m[2].trim(), chunk: m[3] || null, excerpt: m[4].trim() };
    })
    .filter(Boolean);

  if (!cards.length) return { answerHtml: renderMd(rawText.trim()), sourcesHtml: "" };

  const listId = `src-${Date.now()}`;
  const cardItems = cards
    .map(
      (c) => `<div class="source-card">
        <div class="source-card-header">
          <span class="source-card-num">${escapeHtml(c.num)}</span>
          <span class="source-card-name" title="${escapeHtml(c.name)}">${escapeHtml(c.name)}</span>
          ${c.chunk !== null ? `<span class="source-card-chunk">chunk ${escapeHtml(c.chunk)}</span>` : ""}
        </div>
        <div class="source-card-excerpt">${escapeHtml(c.excerpt)}</div>
      </div>`,
    )
    .join("");

  const sourcesHtml = `<div class="source-cards">
    <button class="source-cards-toggle" data-target="${listId}" onclick="toggleSourceCards(this)">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
      ${cards.length} source${cards.length > 1 ? "s" : ""}
    </button>
    <div class="source-cards-list" id="${listId}">${cardItems}</div>
  </div>`;

  return { answerHtml: renderMd(answerPart), sourcesHtml };
}

function toggleSourceCards(btn) {
  btn.classList.toggle("open");
  const list = document.getElementById(btn.dataset.target);
  if (list) list.classList.toggle("open");
}

// ── Messages ──────────────────────────────────────────────────────────────────

function createMsg(role, text) {
  const welcomeEl = document.getElementById("welcome");
  if (welcomeEl && welcomeEl.parentNode) welcomeEl.remove();

  const div = document.createElement("div");
  div.className = `msg msg-${role}`;

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  if (role === "assistant") {
    bubble.innerHTML = text ? renderMd(text) : "";

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

// Thinking spinner (tool-call stage)

function showThinking(bubble) {
  bubble.innerHTML = `
        <div class="thinking">
            <div class="thinking-spinner"></div>
            <span class="thinking-text">Connecting...</span>
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

// Busy

function setBusy(v) {
  busy = v;
  messageInput.disabled = v;
  sendBtn.disabled = v;
}

// Stream

async function streamReply(prompt) {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: prompt, conversation_id: conversationId, new_chat: false }),
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

// Markers that may span multiple network chunks. Keep tail bytes in buffer
// until we're certain they aren't the start of a marker.
const STREAM_MARKERS = ["__THINK__", "__ENDTHINK__"];
const MAX_MARKER_LEN = Math.max(...STREAM_MARKERS.map((m) => m.length));

function splitSafeText(buf) {
  let earliest = -1;
  for (const m of STREAM_MARKERS) {
    const idx = buf.indexOf(m);
    if (idx >= 0 && (earliest < 0 || idx < earliest)) earliest = idx;
  }
  if (earliest >= 0) {
    return { safe: buf.substring(0, earliest), pending: buf.substring(earliest) };
  }
  const maxCheck = Math.min(MAX_MARKER_LEN - 1, buf.length);
  for (let n = maxCheck; n > 0; n--) {
    const tail = buf.substring(buf.length - n);
    if (STREAM_MARKERS.some((m) => m.startsWith(tail))) {
      return { safe: buf.substring(0, buf.length - n), pending: tail };
    }
  }
  return { safe: buf, pending: "" };
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
    let answerStarted = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buf += dec.decode(value, { stream: true });

      while (buf.includes("__THINK__") && buf.includes("__ENDTHINK__")) {
        const si = buf.indexOf("__THINK__");
        const ei = buf.indexOf("__ENDTHINK__");
        if (si < ei) {
          result += buf.substring(0, si);
          const hintText = buf.substring(si + 9, ei);
          updateThinking(bubble, hintText || "Searching...");
          buf = buf.substring(ei + 12);
        } else {
          break;
        }
      }

      const { safe, pending } = splitSafeText(buf);
      if (safe) result += safe;
      buf = pending;

      if (result.trim() && !answerStarted) {
        answerStarted = true;
        hideThinking(bubble);
        bubble.innerHTML = renderMd(result);
      } else if (answerStarted) {
        bubble.innerHTML = renderMd(result);
      }

      scrollToBottom();
    }

    if (buf) result += buf;
    if (!answerStarted) hideThinking(bubble);

    // 流结束后把 Sources 段渲染为折叠卡片
    const finalText = result.trim() || "No answer returned.";
    const { answerHtml, sourcesHtml } = splitAnswerAndSources(finalText);
    bubble.innerHTML = answerHtml;
    if (sourcesHtml) bubble.insertAdjacentHTML("afterend", sourcesHtml);

    upsertConversation();
  } catch (err) {
    hideThinking(bubble);
    bubble.innerHTML = renderMd(`**Error:** ${err.message}`);
    upsertConversation();
  } finally {
    setBusy(false);
    messageInput.focus();
    scrollToBottom();
  }
}

// Events

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
  const deleteBtn = e.target.closest(".history-delete-btn");
  if (deleteBtn) {
    e.stopPropagation();
    deleteConversation(deleteBtn.dataset.id);
    return;
  }
  const btn = e.target.closest(".history-item");
  if (!btn) return;
  loadConversation(btn.dataset.id);
  if (window.innerWidth <= 768) sidebar.classList.add("collapsed");
});

document.getElementById("sidebar-toggle").addEventListener("click", () => {
  sidebar.classList.toggle("collapsed");
});

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
                ${renderSuggestionCards()}
            </div>
        </div>`;
  conversationId = null;
  messageInput.value = "";
  autoResize();
  messageInput.focus();
  bindSuggestionCards(chatLog);
}
document.getElementById("new-chat-btn").addEventListener("click", newChat);

async function checkConfig() {
  try {
    const res = await fetch("/api/config/status");
    const data = await res.json();
    if (!data.dashscope_configured) {
      showToast("Please configure your DashScope API key in Settings.");
    }
  } catch {}
}

// Init
fetchAndRenderHistory();
autoResize();
refreshWelcomeSuggestions();
checkConfig();
messageInput.focus();
