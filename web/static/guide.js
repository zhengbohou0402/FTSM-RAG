// Student Life Guide: topic cards with click-to-ask sample questions + route-map lightbox
// Trilingual UI: LANG is "en" | "zh" | "ms", switched by the topbar toggle and persisted.

let LANG = "en";
try {
  const saved = localStorage.getItem("ftsm_lang");
  if (saved === "zh" || saved === "ms") LANG = saved;
} catch {}
// + an embedded AI assistant drawer (silent guest session — no manual login).
// All card content is data-driven so new topics only need one array entry.

const TOPICS = [
  {
    title: "Visa & EMGS",
    icon: "🛂",
    thumb: "/static/assets/guides/guide-visa.png",
    title_zh: "签证与 EMGS",
    blurb_zh: "学生准证、EMGS 批文、续签时间线，以及出发前要准备什么。",
    questions_zh: ["学生准证快到期了怎么续签？", "新生办理 EMGS 需要哪些材料？"],
    title_ms: "Visa & EMGS",
    blurb_ms: "Pas pelajar, kelulusan EMGS, garis masa pembaharuan dan persediaan sebelum terbang.",
    questions_ms: ["Bagaimana saya memperbaharui pas pelajar sebelum tamat tempoh?", "Apakah dokumen yang diperlukan EMGS untuk pelajar antarabangsa baharu?"],
    image: "/static/assets/guides/story-visa-emgs.jpg",
    blurb:
      "Student pass, EMGS approval, renewal timelines and what to prepare before you fly.",
    questions: [
      "How do I renew my student pass before it expires?",
      "What documents does EMGS require for new international students?",
    ],
  },
  {
    title: "Transport & Buses",
    icon: "🚌",
    thumb: "/static/assets/guides/guide-transport.png",
    title_zh: "交通与巴士",
    blurb_zh: "UKM 校园巴士区间、KTM 通勤火车接驳，以及学生预算下怎么去吉隆坡。",
    questions_zh: ["从 UKM 车站怎么去 FTSM 学院？", "哪一路校园巴士到学生宿舍区？"],
    title_ms: "Pengangkutan & Bas",
    blurb_ms: "Zon bas kampus UKM, sambungan KTM Komuter dan ke KL dalam bajet pelajar.",
    questions_ms: ["Bagaimana pergi dari stesen UKM ke fakulti FTSM?", "Zon bas kampus mana yang menuju ke kolej kediaman pelajar?"],
    image: "/static/assets/guides/story-transport-buses.jpg",
    blurb:
      "UKM campus shuttle zones, KTM komuter connections and getting to KL on a student budget.",
    questions: [
      "How do I get from UKM station to the FTSM faculty?",
      "Which campus bus zone goes to the student dormitories?",
    ],
  },
  {
    title: "Food & Halal",
    icon: "🍜",
    thumb: "/static/assets/guides/guide-food.png",
    title_zh: "美食与清真",
    blurb_zh: "校园周边食堂、嘛嘛档和清真选择——以及大致花费。",
    questions_zh: ["UKM 附近哪里有便宜的清真美食？", "UKM 食堂一顿饭平均多少钱？"],
    title_ms: "Makanan & Halal",
    blurb_ms: "Kantin, gerai mamak dan pilihan halal sekitar kampus — serta kos biasanya.",
    questions_ms: ["Di mana ada makanan halal yang murah berhampiran UKM?", "Berapa kos purata sepinggan makanan di kantin UKM?"],
    image: "/static/assets/guides/story-food-halal.jpg",
    blurb:
      "Cafeterias, mamak stalls and halal options around campus — plus what they typically cost.",
    questions: [
      "Where can I find affordable halal food near UKM?",
      "What is the average cost of a meal at the UKM cafeteria?",
    ],
  },
  {
    title: "Housing",
    icon: "🏠",
    thumb: "/static/assets/guides/guide-housing.png",
    title_zh: "住宿",
    blurb_zh: "校内学院 vs 校外公寓：申请步骤、费用和要带的东西。",
    questions_zh: ["怎么申请 UKM 校内学生住宿？", "入住学生学院前要准备什么？"],
    title_ms: "Penginapan",
    blurb_ms: "Kolej dalam kampus vs hostel swasta: langkah permohonan, yuran dan barang yang perlu dibawa.",
    questions_ms: ["Bagaimana memohon penginapan pelajar dalam kampus UKM?", "Apakah persediaan sebelum masuk ke kolej pelajar?"],
    image: "/static/assets/guides/story-housing.jpg",
    blurb:
      "On-campus colleges vs private hostels: application steps, fees and what to bring.",
    questions: [
      "How do I apply for UKM on-campus student accommodation?",
      "What should I prepare before moving into the student college?",
    ],
  },
  {
    title: "Health & Insurance",
    icon: "🏥",
    thumb: "/static/assets/guides/guide-health.png",
    title_zh: "医疗与保险",
    blurb_zh: "校医院、医疗保险覆盖范围，以及半夜不舒服怎么办。",
    questions_zh: ["UKM 给国际学生提供医疗保险吗？", "校医院在哪里，营业时间几点？"],
    title_ms: "Kesihatan & Insurans",
    blurb_ms: "Klinik kampus, liputan insurans kesihatan dan apa yang perlu dibuat bila tidak siang pada waktu malam.",
    questions_ms: ["Adakah UKM menyediakan insurans kesihatan untuk pelajar antarabangsa?", "Di mana klinik kesihatan kampus dan apakah waktu operasinya?"],
    image: "/static/assets/guides/story-health-insurance.jpg",
    blurb:
      "Campus clinic, health insurance coverage and what to do when you feel unwell at night.",
    questions: [
      "Does UKM provide health insurance for international students?",
      "Where is the campus health clinic and what are its operating hours?",
    ],
  },
  {
    title: "Classes & Academics",
    icon: "📚",
    thumb: "/static/assets/guides/guide-academics.png",
    title_zh: "课业与教务",
    blurb_zh: "选课注册、考试安排、课程表和校历要点。",
    questions_zh: ["新课注册什么时候开放？", "FTSM 的期末考试安排在哪里查？"],
    title_ms: "Kelas & Akademik",
    blurb_ms: "Pendaftaran kursus, jadual peperiksaan, jadual waktu dan perkara penting kalendar akademik.",
    questions_ms: ["Bilakah pendaftaran kursus semester baharu dibuka?", "Di mana saya boleh semak jadual peperiksaan akhir FTSM?"],
    image: "/static/assets/guides/story-classes-academics.jpg",
    blurb:
      "Course registration, exam schedules, timetables and academic calendar highlights.",
    questions: [
      "When does course registration open for the new semester?",
      "Where can I check the final exam schedule for FTSM?",
    ],
  },
];

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function slug(text) {
  return String(text).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function renderCards() {
  const grid = document.getElementById("guide-cards");
  grid.textContent = "";
  TOPICS.forEach((topic) => {
    const slugId = slug(topic.title);
    const card = el("article", "oai-card");
    card.id = "topic-" + slugId;

    if (topic.thumb) {
      const media = el("button", "oai-card-media");
      media.type = "button";
      media.title = "Open the topic page";
      media.addEventListener("click", () => {
        location.hash = `#topic/${slugId}`;
      });
      const img = el("img", "oai-card-img");
      img.src = topic.thumb;
      img.alt = topic.title;
      img.loading = "lazy";
      media.appendChild(img);
      card.appendChild(media);
      card.classList.add("has-media");
    }

    const body = el("div", "oai-card-body");
    const heading = el("button", "oai-card-title", `${topic.icon}  ${pickL(topic, "title")}`);
    heading.type = "button";
    heading.title = "Open the topic page";
    heading.addEventListener("click", () => {
      location.hash = `#topic/${slugId}`;
    });
    body.appendChild(heading);
    body.appendChild(el("p", null, pickL(topic, "blurb")));

    const chips = el("div", "oai-card-links");
    const questions = pickL(topic, "questions");
    questions.forEach((question, qi) => {
      const chip = el("button", "oai-link");
      chip.type = "button";
      chip.textContent = question;
      chip.title = "Read the answer on the topic page";
      chip.addEventListener("click", () => {
        location.hash = `#topic/${slugId}/${qi}`;
      });
      chips.appendChild(chip);
    });
    body.appendChild(chips);
    card.appendChild(body);
    grid.appendChild(card);
  });
}

function setupLightbox() {
  const lightbox = document.getElementById("guide-lightbox");
  const img = document.getElementById("guide-lightbox-img");
  document.querySelectorAll("img[data-zoomable]").forEach((thumb) => {
    thumb.addEventListener("click", () => {
      img.src = thumb.src;
      img.alt = thumb.alt;
      lightbox.hidden = false;
    });
  });
  lightbox.addEventListener("click", () => {
    lightbox.hidden = true;
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") lightbox.hidden = true;
  });
}

// ── View switching (Chat ⇄ Guide ⇄ Topic detail) ──

const VIEWS = ["view-chat", "view-guide", "view-topic"];

function showView(name) {
  VIEWS.forEach((id) => {
    document.getElementById(id).hidden = id !== `view-${name}`;
  });
  const isChat = name === "chat";
  const isTopic = name === "topic";
  document.getElementById("tab-chat").classList.toggle("active", isChat);
  document.getElementById("tab-guide").classList.toggle("active", !isChat);
  try {
    if (!isTopic) history.replaceState(null, "", isChat ? "#chat" : "#guide");
  } catch {
    // older browsers — non-critical
  }
  if (isChat) {
    document.getElementById("assistant-message").focus();
    refreshHistory();
  } else {
    window.scrollTo(0, 0);
  }
}

function switchView(view) {
  showView(view === "guide" ? "guide" : "chat");
}

// Topic detail pages: /guide#topic/<slug>[/<questionIndex>]
const TOPIC_DATA = { fetched: null };

function loadTopicData() {
  if (!TOPIC_DATA.fetched) {
    TOPIC_DATA.fetched = fetch("/static/topic_answers.json?v=20261010e")
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
      .catch((err) => {
        TOPIC_DATA.fetched = null; // allow retry on next navigation
        throw err;
      });
  }
  return TOPIC_DATA.fetched;
}

function chatMsgFor(text) {
  // Switch to chat with the question prefilled and sent.
  showView("chat");
  sendMessage(text);
}

async function showTopic(slugId, questionIndex) {
  showView("topic");
  const topic = TOPICS.find((t) => slug(t.title) === slugId);
  const titleEl = document.getElementById("topic-title");
  const subEl = document.getElementById("topic-sub");
  const imgEl = document.getElementById("topic-hero-img");
  const container = document.getElementById("topic-answers");
  container.innerHTML = "";

  if (!topic) {
    titleEl.textContent = t3("Topic not found", "未找到话题", "Topik tidak ditemui");
    subEl.textContent = "";
    imgEl.src = "";
    container.appendChild(el("p", "story-note", t3("This topic does not exist. Go back to the guide.", "话题不存在，请返回指南页。", "Topik ini tidak wujud. Kembali ke halaman panduan.")));
    return;
  }

  const showTitle = pickL(topic, "title");
  titleEl.textContent = showTitle;
  subEl.textContent = pickL(topic, "blurb");
  imgEl.src = topic.image;
  imgEl.alt = `Illustration: ${showTitle}`;

  let data = null;
  try {
    data = await loadTopicData();
  } catch {
    data = null; // fall through to per-question fallback below
  }
  const topicData = data && data.topics ? data.topics[slugId] : null;

  topic.questions.forEach((question, qi) => {
    const showQ = pickL(topic, "questions")[qi] || question;
    const section = el("section", "story-qa");
    section.id = `topic-${slugId}-${qi}`;
    const q = el("h2", "story-q", showQ);
    section.appendChild(q);

    const answerBox = el("div", "story-answer markdown");
    const answer = topicData && topicData.answers ? topicData.answers[question] : null;
    if (answer) {
      answerBox.innerHTML = renderAnswer(answer);
    } else {
      answerBox.classList.remove("markdown");
      answerBox.textContent = t3(
        "This answer has not been generated yet — ask it in the chat and the assistant will answer live.",
        "该答案尚未生成——去聊天里提问，助手会实时回答。",
        "Jawapan ini belum dijana — tanyakan dalam sembang dan pembantu akan menjawab serta-merta."
      );
    }
    section.appendChild(answerBox);

    const askBtn = el("button", "oai-link", t3("Ask a follow-up in chat", "回聊天里追问", "Tanya susulan dalam sembang"));
    askBtn.type = "button";
    askBtn.addEventListener("click", () => chatMsgFor(showQ));
    section.appendChild(askBtn);

    container.appendChild(section);
  });

  window.scrollTo(0, 0);
  if (questionIndex != null) {
    const anchor = document.getElementById(`topic-${slugId}-${questionIndex}`);
    if (anchor) {
      window.setTimeout(() => anchor.scrollIntoView({ behavior: "smooth" }), 60);
    }
  }
}

const GUIDE_ANCHORS = new Set(["#guide", "#topics", "#programmes", "#checklist", "#trending", "#how-it-works", "#buses"]);

function applyHash() {
  const hash = location.hash || "";
  if (hash.startsWith("#topic/")) {
    const rest = hash.slice("#topic/".length);
    const parts = rest.split("/");
    showTopic(parts[0], parts[1] != null && parts[1] !== "" ? parseInt(parts[1], 10) : null);
    return;
  }
  if (GUIDE_ANCHORS.has(hash)) {
    switchView("guide");
    if (hash !== "#guide") {
      const target = document.querySelector(hash);
      if (target) setTimeout(() => target.scrollIntoView({ behavior: "smooth" }), 50);
    }
    return;
  }
  switchView("chat");
}

// ── AI assistant (silent guest session, no manual login) ──

const ASSISTANT = {
  conversationId: sessionStorage.getItem("ftsm_conversation_id") || null,
  authenticated: false,
  pendingQuestion: null,
  sending: false,
  ensuring: null, // shared in-flight session promise
};

function scrollChatToEnd() {
  const scroller = document.getElementById("chat-scroll");
  scroller.scrollTop = scroller.scrollHeight;
}

// Minimal markdown renderer for assistant answers (bold / italic / inline code /
// headings / hr / bullet & ordered lists). Input is escaped first, so model output
// can never inject HTML.
function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function renderMarkdown(text) {
  const inline = (s) =>
    s
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[\s(])\*([^*\n]+)\*/g, "$1<em>$2</em>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\[\s*(References?\b[^\]]*)\]/g, '<span class="cite">[$1]</span>');

  const lines = escapeHtml(String(text)).split("\n");
  let html = "";
  let list = null; // null | "ul" | "ol"
  const closeList = () => {
    if (list) {
      html += "</" + list + ">";
      list = null;
    }
  };
  for (const raw of lines) {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*[-*]\s+(.*)$/);
    const ordered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (bullet) {
      if (list !== "ul") {
        closeList();
        html += "<ul>";
        list = "ul";
      }
      html += "<li>" + inline(bullet[1]) + "</li>";
      continue;
    }
    if (ordered) {
      if (list !== "ol") {
        closeList();
        html += "<ol>";
        list = "ol";
      }
      html += "<li>" + inline(ordered[1]) + "</li>";
      continue;
    }
    closeList();
    if (/^#{1,6}\s+/.test(line)) {
      html += "<h3>" + inline(line.replace(/^#{1,6}\s+/, "")) + "</h3>";
    } else if (/^---+\s*$/.test(line)) {
      html += "<hr>";
    } else if (line.trim()) {
      html += "<p>" + inline(line) + "</p>";
    }
  }
  closeList();
  return html;
}

// Answers end with a "Sources:" block listing [n] file (Chunk k) lines.
// Render the body as markdown and turn that block into a horizontal row of
// compact Perplexity-style source tiles below the answer text.
function renderAnswer(text) {
  const lines = String(text).split("\n");
  let srcIdx = -1;
  for (let i = lines.length - 1; i >= 0; i--) {
    if (/^\s*(?:#{1,6}\s*)?\*{0,2}\s*sources:?\s*\*{0,2}\s*$/i.test(lines[i])) {
      srcIdx = i;
      break;
    }
  }
  if (srcIdx === -1) return renderMarkdown(text);

  // Source lines format:
  // - [1] file.txt [Official material], chunk 2: excerpt
  // - [1] file.txt (Chunk 2)
  // - file.txt
  const chipRe = /^\s*[-*]?\s*(?:\[(\d+)\]\s*)?(\S+?)(?:\s+\[([^\]]+)\])?(?:,\s*chunk\s*(\d+))?(?:\s*\(([^)]+)\))?(?::\s*(.*))?$/i;
  const FILE_ICON =
    '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" ' +
    'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<path d="M14 2H7a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7z"/>' +
    '<path d="M14 2v5h5"/><path d="M9 13h6"/><path d="M9 17h6"/></svg>';
  let rows = "";
  for (const raw of lines.slice(srcIdx + 1)) {
    const line = raw.trim();
    if (!line || /^#{1,6}\s/.test(line)) continue;
    const m = line.match(chipRe);
    if (!m || !m[2]) continue;
    const num = m[1] || "";
    const name = escapeHtml(m[2].replace(/`/g, "").trim());
    let meta = "";
    if (m[3] && m[4]) {
      meta = m[3] + " · Chunk " + m[4];
    } else if (m[3]) {
      meta = m[3];
    } else if (m[4]) {
      meta = "Chunk " + m[4];
    } else if (m[5]) {
      meta = m[5];
    }
    meta = escapeHtml(meta.replace(/`/g, "").trim());
    const excerpt = m[6] ? escapeHtml(m[6].replace(/`/g, "").trim()) : "";
    const titleAttr = excerpt ? ' title="' + excerpt + '"' : (meta ? ' title="' + meta + '"' : "");
    const lead = num
      ? '<span class="source-num">' + num + "</span>"
      : '<span class="source-icon">' + FILE_ICON + "</span>";
    rows +=
      '<div class="source-item"' + titleAttr + ">" +
      lead +
      '<span class="source-name">' + name + "</span>" +
      (meta ? '<span class="source-desc">' + meta + "</span>" : "") +
      "</div>";
  }
  if (!rows) return renderMarkdown(text);
  const count = rows.split('class="source-item"').length - 1;
  const bodyLines = lines.slice(0, srcIdx).filter((l) => !/^\s*source reliability:/i.test(l));
  // Sources stay BELOW the answer body (user preference), Perplexity-style
  // tiles are kept for the visuals only.
  return (
    renderMarkdown(bodyLines.join("\n")) +
    '<div class="sources-block">' +
    '<div class="sources-head"><span>' + t3("Sources", "来源", "Sumber") + "</span>" +
    '<span class="sources-count">' + count + "</span></div>" +
    '<div class="source-list">' + rows + "</div></div>"
  );
}

function setAssistantStatus(text) {
  document.getElementById("assistant-status").textContent = text;
}

// Persistent per-browser guest identity (localStorage) so conversations and
// query logs stay tied to the same visitor across refreshes.
function guestCredentials() {
  let creds = null;
  try {
    creds = JSON.parse(localStorage.getItem("ftsm_guest") || "null");
  } catch {
    creds = null;
  }
  if (creds && creds.studentId && creds.password) return creds;
  creds = {
    studentId: "guest_" + Math.random().toString(36).slice(2, 12),
    password:
      Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2),
  };
  try {
    localStorage.setItem("ftsm_guest", JSON.stringify(creds));
  } catch {
    // Private mode may block localStorage — session still works for this visit.
  }
  return creds;
}

async function authPost(path, creds) {
  const res = await fetch(path, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(creds),
  });
  return res;
}

// Ensure a valid session exists without any user interaction:
// 1) existing cookie -> done; 2) register guest (register also sets the cookie);
// 3) guest id already taken -> login with stored password; 4) password mismatch
// (stale identity) -> rotate to a fresh guest once.
async function ensureSession(force = false) {
  if (ASSISTANT.authenticated && !force) return true;
  if (ASSISTANT.ensuring) return ASSISTANT.ensuring;

  ASSISTANT.ensuring = (async () => {
    setAssistantStatus("Preparing your session…");
    if (!force) {
      try {
        const res = await fetch("/api/auth/me", { credentials: "include" });
        if (res.ok) {
          const data = await res.json();
          if (data.authenticated) {
            ASSISTANT.authenticated = true;
            setAssistantStatus("Online · knowledge base ready");
            return true;
          }
        }
      } catch {
        // network hiccup — fall through to guest creation
      }
    }

    for (let attempt = 0; attempt < 2; attempt++) {
      const creds = guestCredentials();
      const reg = await authPost("/api/auth/register", creds);
      if (reg.ok) {
        ASSISTANT.authenticated = true;
        setAssistantStatus("Online · knowledge base ready");
        return true;
      }
      if (reg.status === 409) {
        const login = await authPost("/api/auth/login", creds);
        if (login.ok) {
          ASSISTANT.authenticated = true;
          setAssistantStatus("Online · knowledge base ready");
          return true;
        }
      }
      // Identity is unusable (e.g. stale localStorage) — rotate and retry once.
      try {
        localStorage.removeItem("ftsm_guest");
      } catch {}
    }
    setAssistantStatus("Session unavailable — please retry");
    return false;
  })();

  try {
    return await ASSISTANT.ensuring;
  } finally {
    ASSISTANT.ensuring = null;
  }
}

function addMessage(role, text, isError) {
  const wrap = document.getElementById("assistant-messages");
  const bubble = el("div", `chat-msg ${role}${isError ? " error" : ""}`);
  bubble.textContent = text;
  wrap.appendChild(bubble);
  scrollChatToEnd();
  return bubble;
}

function showTypingIn(bubble, statusText) {
  bubble.textContent = "";
  const dots = el("span", "typing-dots");
  dots.append(el("i"), el("i"), el("i"));
  if (statusText) bubble.append(document.createTextNode(statusText + " "));
  bubble.append(dots);
  scrollChatToEnd();
}

async function askAssistant(question) {
  switchView("chat");
  sendMessage(question);
}

async function sendMessage(text, isRetry = false) {
  const message = (text || "").trim();
  if (!message) return;

  // 守卫必须在**任何 await 之前**同步占位。
  // 原实现是「先 await ensureSession() 再置 ASSISTANT.sending = true」，
  // 这段窗口里第二次回车会同时通过检查 → 两个 /api/chat 请求、两条用户气泡、
  // 一个孤儿打字气泡。另外它还会让 401 自动重试变成死代码：重试走的是
  // sendMessage(message, true)，而此刻 sending 仍为 true，守卫直接把重试吞掉，
  // 气泡又已在上面被 remove，用户看到的是"提问凭空消失、没有回答"。
  if (ASSISTANT.sending) return;
  ASSISTANT.sending = true;

  const input = document.getElementById("assistant-message");
  const send = document.getElementById("assistant-send");
  let bubble = null;

  try {
    const ready = await ensureSession();
    if (!ready) {
      addMessage("bot", "I could not start a session just now — please try again in a moment.", true);
      return;
    }

    if (!isRetry) {
      input.value = "";
      document.getElementById("chat-empty").hidden = true;
      addMessage("user", message);
    }
    send.disabled = true;
    bubble = addTypingBubble();

    const res = await fetch("/api/chat", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        conversation_id: ASSISTANT.conversationId || undefined,
      }),
    });

    if (res.status === 401 && !isRetry) {
      bubble.remove();
      bubble = null;
      ASSISTANT.authenticated = false;
      const ok = await ensureSession(true);
      if (ok) {
        ASSISTANT.sending = false; // 释放守卫，否则递归调用的入口检查会把重试丢掉
        await sendMessage(message, true); // auto-retry once with the fresh session
      } else {
        addMessage("bot", "Session expired and could not be renewed — please try again.", true);
      }
      return;
    }
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `Chat failed (${res.status})`);
    }

    const conversationId = res.headers.get("X-Conversation-Id");
    if (conversationId) {
      ASSISTANT.conversationId = conversationId;
      sessionStorage.setItem("ftsm_conversation_id", conversationId);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let answer = "";
    // Re-render markdown as chunks arrive (throttled) so the answer formats
    // live instead of showing raw ### / ** until the stream ends.
    let lastPaint = 0;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      answer += decoder.decode(value, { stream: true });
      // The stream interleaves "__THINK__<status>__ENDTHINK__" status markers.
      // Hide completed ones; show an open marker's text as the typing indicator.
      let display = answer.replace(/__THINK__[\s\S]*?__ENDTHINK__/g, "");
      const openIdx = display.indexOf("__THINK__");
      const now = performance.now();
      if (openIdx !== -1) {
        const status = display.slice(openIdx + "__THINK__".length).trim();
        showTypingIn(bubble, status);
      } else if (display && now - lastPaint > 60) {
        lastPaint = now;
        bubble.classList.add("markdown");
        bubble.innerHTML = renderAnswer(display);
      } else if (!display) {
        showTypingIn(bubble, "");
      }
      scrollChatToEnd();
    }

    const finalText = answer.replace(/__THINK__[\s\S]*?__ENDTHINK__/g, "").trim();
    if (!finalText) {
      bubble.textContent = "The assistant returned an empty answer — please try again.";
    } else if (finalText.includes("[Error]")) {
      bubble.classList.add("error");
      bubble.textContent = finalText;
    } else {
      bubble.classList.add("markdown");
      bubble.innerHTML = renderAnswer(finalText);
      attachSpeakButton(bubble, finalText);
    }
  } catch (error) {
    if (bubble) {
      bubble.classList.add("error");
      bubble.textContent = `Network error: ${error.message}`;
    } else {
      addMessage("bot", `Network error: ${error.message}`, true);
    }
  } finally {
    ASSISTANT.sending = false;
    send.disabled = false;
    input.focus();
    refreshHistory(); // update the sidebar with the latest title/time
  }
}

function addTypingBubble() {
  const wrap = document.getElementById("assistant-messages");
  const bubble = el("div", "chat-msg bot");
  showTypingIn(bubble, "");
  wrap.appendChild(bubble);
  scrollChatToEnd();
  return bubble;
}

function resetConversation() {
  ASSISTANT.conversationId = null;
  sessionStorage.removeItem("ftsm_conversation_id");
  document.getElementById("assistant-messages").innerHTML = "";
  document.getElementById("chat-empty").hidden = false;
  renderHistoryList();
  closeSidebarOnMobile();
}

// ── Conversation history sidebar ──

const HISTORY = { items: [] };

function fmtTime(sec) {
  const ms = Number(sec || 0) * 1000;
  if (!ms) return "";
  const d = new Date(ms);
  const today = new Date();
  return d.toDateString() === today.toDateString()
    ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString([], { month: "short", day: "numeric" });
}

async function refreshHistory() {
  const ready = await ensureSession().catch(() => false);
  if (!ready) return;
  try {
    const res = await fetch("/api/conversations", { credentials: "include" });
    if (!res.ok) return;
    const data = await res.json();
    HISTORY.items = Array.isArray(data.items) ? data.items : [];
    renderHistoryList();
  } catch {
    // history is best-effort — ignore failures
  }
}

function renderHistoryList() {
  const list = document.getElementById("sidebar-list");
  if (!list) return;
  list.innerHTML = "";
  if (!HISTORY.items.length) {
    list.appendChild(el("p", "sidebar-empty", "No conversations yet"));
    return;
  }
  HISTORY.items.forEach((item) => {
    const row = el("button", "sidebar-item");
    row.type = "button";
    if (item.id === ASSISTANT.conversationId) row.classList.add("active");
    row.title = item.title || "New chat";
    row.append(el("span", "sidebar-item-title", item.title || "New chat"));
    row.append(el("span", "sidebar-item-time", fmtTime(item.updated_at)));

    const del = el("span", "sidebar-item-del", "×");
    del.title = "Delete conversation";
    del.addEventListener("click", (event) => {
      event.stopPropagation();
      deleteConversation(item.id);
    });
    row.append(del);

    row.addEventListener("click", () => openConversation(item.id));
    list.appendChild(row);
  });
}

async function openConversation(id) {
  const ready = await ensureSession();
  if (!ready) {
    setAssistantStatus("Session unavailable — please retry");
    return;
  }
  try {
    const res = await fetch(`/api/conversations/${encodeURIComponent(id)}`, {
      credentials: "include",
    });
    if (!res.ok) throw new Error(String(res.status));
    const data = await res.json();
    ASSISTANT.conversationId = data.id;
    sessionStorage.setItem("ftsm_conversation_id", data.id);

    const wrap = document.getElementById("assistant-messages");
    wrap.innerHTML = "";
    document.getElementById("chat-empty").hidden = true;
    (data.messages || []).forEach((m) => {
      const bubble = el("div", `chat-msg ${m.role === "user" ? "user" : "bot"}`);
      if (m.role === "assistant") {
        bubble.classList.add("markdown");
        bubble.innerHTML = renderAnswer(m.content || "");
        attachSpeakButton(bubble, m.content);
      } else {
        bubble.textContent = m.content || "";
      }
      wrap.appendChild(bubble);
    });
    scrollChatToEnd();
    renderHistoryList();
    closeSidebarOnMobile();
  } catch {
    setAssistantStatus("Could not load that conversation");
  }
}

async function deleteConversation(id) {
  try {
    await fetch(`/api/conversations/${encodeURIComponent(id)}`, {
      method: "DELETE",
      credentials: "include",
    });
  } catch {
    // ignore network errors — refresh will reconcile
  }
  if (ASSISTANT.conversationId === id) resetConversation();
  await refreshHistory();
}

function newChat() {
  resetConversation();
  document.getElementById("assistant-message").focus();
}

function toggleSidebar() {
  document.getElementById("chat-sidebar").classList.toggle("open");
}

function closeSidebarOnMobile() {
  document.getElementById("chat-sidebar").classList.remove("open");
}

// ── Live knowledge-base stats ───────────────────────────

async function loadStats() {
  const strip = document.getElementById("guide-stats");
  try {
    const [statsRes, healthRes] = await Promise.all([
      fetch("/api/kb/stats"),
      fetch("/api/health"),
    ]);
    if (!statsRes.ok) return;
    const stats = await statsRes.json();
    document.getElementById("stat-docs").textContent = stats.document_count ?? "–";
    document.getElementById("stat-chunks").textContent = stats.total_chunks ?? "–";
    document.getElementById("stat-cache").textContent = stats.cache_entries ?? "–";
    let status = "Degraded";
    try {
      const health = await healthRes.json();
      const ok = String(health.status || health.state || "").toLowerCase();
      status = ok.includes("ok") || ok.includes("healthy") ? "Online" : ok || "Degraded";
    } catch {
      status = "Degraded";
    }
    document.getElementById("stat-status").textContent = status;
    strip.hidden = false;
  } catch {
    // stats are decorative — leave the strip hidden on failure
  }
}

// ── Pre-departure checklist (localStorage-persisted) ────

const CHECKLIST_ITEMS = [
  "Passport valid for at least 12 months",
  "EMGS approval letter and offer letter printed",
  "Student pass / VAL documents in hand luggage",
  "Health insurance coverage confirmed",
  "Passport-size photos (white background)",
  "Type G plug adapter (UK-style, 240 V)",
  "Medicine with English prescription labels",
  "Some Ringgit (RM) cash for the first days",
  "UKM accommodation check-in details saved offline",
  "Emergency numbers saved (Malaysia: 999)",
];
const CHECKLIST_KEY = "ftsm_checklist_v1";
// 中文显示文案（下标与 CHECKLIST_ITEMS 一一对应；勾选状态仍按英文原文存取）
const CHECKLIST_ITEMS_ZH = [
  "护照有效期至少 12 个月",
  "EMGS 批文与录取通知书打印件",
  "学生准证 / VAL 文件随身行李",
  "医疗保险已确认生效",
  "白底证件照若干",
  "英标 Type G 转换插头（240V）",
  "药品附英文处方说明",
  "首几天用的零令吉（RM）现金",
  "UKM 住宿入住信息已离线保存",
  "紧急电话已保存（马来西亚：999）",
];
// 马来语显示文案（下标与 CHECKLIST_ITEMS 一一对应；勾选状态仍按英文原文存取）
const CHECKLIST_ITEMS_MS = [
  "Pasport sah sekurang-kurangnya 12 bulan",
  "Surat kelulusan EMGS dan surat tawaran dicetak",
  "Dokumen pas pelajar / VAL dalam bagasi tangan",
  "Liputan insurans kesihatan disahkan",
  "Gambar bersaiz pasport (latar belakang putih)",
  "Penyesuai palam Jenis G (gaya UK, 240 V)",
  "Ubat dengan label preskripsi berbahasa Inggeris",
  "Wang tunai Ringgit (RM) untuk hari-hari awal",
  "Maklumat daftar masuk penginapan UKM disimpan luar talian",
  "Nombor kecemasan disimpan (Malaysia: 999)",
];

function loadChecklistState() {
  try {
    return JSON.parse(localStorage.getItem(CHECKLIST_KEY) || "{}");
  } catch {
    return {};
  }
}

function saveChecklistState(state) {
  try {
    localStorage.setItem(CHECKLIST_KEY, JSON.stringify(state));
  } catch {
    // private mode — checklist still works for this visit
  }
}

function renderChecklist() {
  const list = document.getElementById("checklist-items");
  list.textContent = "";
  const state = loadChecklistState();
  CHECKLIST_ITEMS.forEach((item, idx) => {
    const li = el("li");
    const label = el("label");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = !!state[item];
    box.addEventListener("change", () => {
      const current = loadChecklistState();
      current[item] = box.checked;
      saveChecklistState(current);
    });
    const text = el("span", null, LANG === "zh" ? (CHECKLIST_ITEMS_ZH[idx] || item) : LANG === "ms" ? (CHECKLIST_ITEMS_MS[idx] || item) : item);
    label.append(box, text);
    li.appendChild(label);
    list.appendChild(li);
  });
  document.getElementById("checklist-reset").onclick = () => {
    saveChecklistState({});
    list.querySelectorAll("input[type='checkbox']").forEach((box) => {
      box.checked = false;
    });
  };
}

// ── Programmes at FTSM (real data from the knowledge base) ──
// Names and admission facts come from data/ukm_ftsm/programmes_and_admissions.txt
// (official ftsm.ukm.my pages). Time-sensitive intake windows are intentionally
// excluded — always verify on official channels.

const PROGRAMMES = [
  {
    name: "Bachelor in Computer Science (Honours)",
    level: "Undergraduate",
    name_zh: "计算机科学学士（荣誉）",
    level_zh: "本科",
    image: "/static/assets/guides/banner-campus.png",
    blurb:
      "Flagship computing degree of the faculty. Full-time applications go through the Ministry of Higher Education Malaysia online process.",
    blurb_zh: "学院旗舰计算类学位。全日制申请经马来西亚高等教育部线上流程进行。",
    name_ms: "Ijazah Sarjana Muda Sains Komputer (Kepujian)",
    level_ms: "Prasiswazah",
    blurb_ms: "Ijazah komputer utama fakulti. Permohonan sepenuh masa melalui proses dalam talian Kementerian Pengajian Tinggi Malaysia.",
  },
  {
    name: "Bachelor in Information Technology (Honours)",
    level: "Undergraduate",
    name_zh: "信息技术学士（荣誉）",
    level_zh: "本科",
    image: "/static/assets/guides/banner-kl.png",
    blurb:
      "Broad information technology degree covering systems and technology management practice.",
    blurb_zh: "覆盖系统与技术管理实践的宽口径信息技术学位。",
    name_ms: "Ijazah Sarjana Muda Teknologi Maklumat (Kepujian)",
    level_ms: "Prasiswazah",
    blurb_ms: "Ijazah teknologi maklumat yang luas merangkumi amalan pengurusan sistem dan teknologi.",
  },
  {
    name: "Bachelor in Software Engineering (Honours)",
    level: "Undergraduate",
    name_zh: "软件工程学士（荣誉）",
    level_zh: "本科",
    image: "/static/assets/guides/banner-success.png",
    blurb:
      "Accredited variants include Multimedia System Development and Information System Development.",
    blurb_zh: "含多媒体系统开发与信息系统开发等经认证方向。",
    name_ms: "Ijazah Sarjana Muda Kejuruteraan Perisian (Kepujian)",
    level_ms: "Prasiswazah",
    blurb_ms: "Varian terakredit termasuk Pembangunan Sistem Multimedia dan Pembangunan Sistem Maklumat.",
  },
  {
    name: "11 master's programmes",
    level: "Postgraduate",
    name_zh: "11 个硕士项目",
    level_zh: "研究生",
    image: "/static/assets/guides/story-classes-academics.jpg",
    blurb:
      "Including Artificial Intelligence, Data Science, Cyber Security, Health Informatics, Software Engineering, Information Science and more — offered by coursework, mixed or research modes.",
    blurb_zh: "包括人工智能、数据科学、网络安全、健康信息学、软件工程、信息科学等——提供课程制、混合制与研究制。",
    name_ms: "11 program sarjana",
    level_ms: "Pascasiswazah",
    blurb_ms: "Termasuk Kecerdasan Buatan (AI), Sains Data, Keselamatan Siber, Informatik Kesihatan, Kejuruteraan Perisian, Sains Maklumat dan banyak lagi — mod coursework, campuran atau penyelidikan.",
  },
];

function renderProgrammes() {
  const grid = document.getElementById("programme-grid");
  if (!grid) return;
  grid.textContent = "";
  PROGRAMMES.forEach((programme) => {
    const card = el("article", "oai-card");
    const body = el("div", "oai-card-body");
    body.appendChild(el("span", "oai-badge", pickL(programme, "level")));
    body.appendChild(el("h3", null, pickL(programme, "name")));
    body.appendChild(el("p", null, pickL(programme, "blurb")));

    const ask = el("button", "oai-link", t3("Ask about this", "问问这个专业", "Tanya tentang program ini"));
    ask.type = "button";
    const pname = pickL(programme, "name");
    ask.addEventListener("click", () =>
      askAssistant(
        LANG === "zh"
          ? `介绍一下 FTSM UKM 的${pname}`
          : LANG === "ms"
          ? `Terangkan tentang ${pname} di FTSM UKM`
          : `Tell me about the ${programme.name} at FTSM UKM`
      )
    );
    body.appendChild(ask);

    card.appendChild(body);
    grid.appendChild(card);
  });
}

function setupChat() {
  document.querySelectorAll(".topbar-tab").forEach((tab) => {
    tab.addEventListener("click", () => switchView(tab.dataset.view));
  });
  document.getElementById("assistant-new-chat").addEventListener("click", resetConversation);
  document.getElementById("sidebar-newchat").addEventListener("click", newChat);
  document.getElementById("sidebar-toggle").addEventListener("click", toggleSidebar);
  document.getElementById("guide-ask").addEventListener("click", () => switchView("chat"));
  document.getElementById("topic-ask").addEventListener("click", () => switchView("chat"));

  document.getElementById("assistant-input-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = document.getElementById("assistant-message");
    sendMessage(input.value);
  });

  renderSuggestions();
  window.addEventListener("hashchange", applyHash);
  applyHash();
  ensureSession().catch(() => setAssistantStatus("Offline — please retry"));
}

let _cachedTrending = [];

function renderTrending() {
  const section = document.getElementById("trending");
  const grid = document.getElementById("trend-grid");
  if (!grid || !section || !_cachedTrending.length) return;
  grid.textContent = "";
  _cachedTrending.forEach((item) => {
    const chip = el("button", "trend-chip");
    chip.type = "button";
    chip.append(el("span", null, item.question));
    chip.append(el("span", "trend-count", `×${item.count}`));
    chip.title = t3("Click to ask the assistant", "点击直接提问", "Klik untuk tanya pembantu");
    chip.addEventListener("click", () => askAssistant(item.question));
    grid.appendChild(chip);
  });
  section.hidden = false;
}

// OpenAI-style suggestion chips under the greeting (one per topic).
function renderSuggestions() {
  const wrap = document.getElementById("chat-suggestions");
  if (!wrap) return;
  wrap.textContent = "";
  TOPICS.forEach((topic) => {
    const question = pickL(topic, "questions")[0] || topic.questions[0];
    const chip = el("button", "chat-suggest");
    chip.type = "button";
    chip.append(el("span", "chat-suggest-icon", topic.icon), el("span", null, question));
    chip.addEventListener("click", () => sendMessage(question));
    wrap.appendChild(chip);
  });
}

// ── Trending questions (from the Java query_log via the gateway) ──

async function loadTrending() {
  try {
    const res = await fetch("/api/knowledge/popular");
    if (!res.ok) return;
    const data = await res.json();
    _cachedTrending = (data.items || []).filter((it) => {
      const q = (it.question || "").trim();
      return q.length >= 6 && q.toLowerCase() !== "warmup";
    });
    if (!_cachedTrending.length) return;
    renderTrending();
  } catch {
    // trending is decorative — ignore failures
  }
}

renderCards();
setupLightbox();
setupChat();
loadStats();
renderChecklist();
loadTrending();
renderProgrammes();
// ── Voice: read aloud (TTS) + voice input (STT) ──

const SPEAKER_SVG =
  '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" /><path d="M15.5 8.5a5 5 0 0 1 0 7" /><path d="M18.5 5.5a9 9 0 0 1 0 13" /></svg>';

let currentAudio = null;
let currentSpeakBtn = null;
let currentTtsUrl = null; // P3：TTS Blob URL，停止/播完必须 revoke，否则内存泄漏

function stopSpeaking() {
  if (currentAudio) {
    try { currentAudio.pause(); } catch {}
    currentAudio = null;
  }
  if (currentTtsUrl) {
    try { URL.revokeObjectURL(currentTtsUrl); } catch {}
    currentTtsUrl = null;
  }
  if (currentSpeakBtn) {
    currentSpeakBtn.classList.remove("speaking", "loading");
    currentSpeakBtn = null;
  }
}

function attachSpeakButton(bubble, rawText) {
  const text = (rawText || "").trim();
  if (!text) return;
  const btn = el("button", "speak-btn");
  btn.type = "button";
  btn.title = "Read aloud";
  btn.setAttribute("aria-label", "Read aloud");
  btn.innerHTML = SPEAKER_SVG;
  btn.addEventListener("click", async () => {
    if (currentSpeakBtn === btn) { stopSpeaking(); return; }
    stopSpeaking();
    btn.classList.add("loading");
    try {
      const res = await fetch("/api/voice/tts", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) throw new Error(`TTS ${res.status}`);
      const blob = await res.blob();
      currentTtsUrl = URL.createObjectURL(blob);
      const audio = new Audio(currentTtsUrl);
      currentAudio = audio;
      currentSpeakBtn = btn;
      btn.classList.remove("loading");
      btn.classList.add("speaking");
      audio.onended = () => { if (currentSpeakBtn === btn) stopSpeaking(); };
      await audio.play();
    } catch (err) {
      btn.classList.remove("loading");
      setAssistantStatus("Could not generate audio — please retry");
    }
  });
  bubble.appendChild(btn);
}

// ── Voice input: capture 16 kHz mono PCM and encode WAV in the browser ──

const MicRecorder = {
  stream: null, ctx: null, processor: null, source: null,
  chunks: [], recording: false,
  async start() {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
    this.ctx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    this.source = this.ctx.createMediaStreamSource(this.stream);
    this.processor = this.ctx.createScriptProcessor(4096, 1, 1);
    this.chunks = [];
    this.processor.onaudioprocess = (e) => {
      if (this.recording) this.chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
    };
    this.source.connect(this.processor);
    this.processor.connect(this.ctx.destination);
    this.recording = true;
  },
  stop() {
    this.recording = false;
    try { this.source.disconnect(); this.processor.disconnect(); } catch {}
    if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
    const sampleRate = this.ctx ? this.ctx.sampleRate : 16000;
    try { if (this.ctx) this.ctx.close(); } catch {}
    const total = this.chunks.reduce((n, c) => n + c.length, 0);
    const pcm = new Float32Array(total);
    let off = 0;
    for (const c of this.chunks) { pcm.set(c, off); off += c.length; }
    this.chunks = [];
    return { pcm, sampleRate };
  },
};

function floatToWav(pcm, sampleRate) {
  const buf = new ArrayBuffer(44 + pcm.length * 2);
  const view = new DataView(buf);
  const w = (off, s) => { for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i)); };
  w(0, "RIFF"); view.setUint32(4, 36 + pcm.length * 2, true); w(8, "WAVEfmt ");
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  w(36, "data"); view.setUint32(40, pcm.length * 2, true);
  let o = 44;
  for (let i = 0; i < pcm.length; i++, o += 2) {
    const s = Math.max(-1, Math.min(1, pcm[i]));
    view.setInt16(o, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([view], { type: "audio/wav" });
}

let voiceBusy = false;

async function toggleVoiceInput() {
  if (voiceBusy) return;
  const mic = document.getElementById("voice-mic");
  const input = document.getElementById("assistant-message");
  if (!MicRecorder.recording) {
    try {
      await MicRecorder.start();
      mic.classList.add("recording");
      input.placeholder = "Listening… click again to stop";
      input.value = "";
    } catch {
      setAssistantStatus("Microphone unavailable — check browser permissions");
    }
    return;
  }
  // stop -> transcribe
  voiceBusy = true;
  mic.classList.remove("recording");
  mic.classList.add("transcribing");
  const { pcm, sampleRate } = MicRecorder.stop();
  input.placeholder = "Transcribing…";
  const durationMs = (pcm.length * 1000) / sampleRate;
  try {
    if (durationMs < 600) {
      input.placeholder = "Clip too short — hold a little longer";
      return;
    }
    const form = new FormData();
    form.append("audio", floatToWav(pcm, sampleRate), "speech.wav");
    const res = await fetch("/api/voice/stt", { method: "POST", body: form, credentials: "include" });
    if (!res.ok) throw new Error(`STT ${res.status}`);
    const data = await res.json();
    if (data.text) {
      input.value = data.text;
      input.focus();
    } else {
      input.placeholder = "Nothing heard — try again";
    }
  } catch (err) {
    input.placeholder = "Transcription failed — please type instead";
    setAssistantStatus("Voice input failed — please retry");
  } finally {
    mic.classList.remove("transcribing");
    if (input.placeholder.startsWith("Transcribing")) input.placeholder = "Ask about visas, buses, food…";
    voiceBusy = false;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const mic = document.getElementById("voice-mic");
  if (mic) mic.addEventListener("click", toggleVoiceInput);
});

// ── Training materials drawer ────────────────────────────────────────────────
// Lets a student drop in their own notes, then rebuild the vector index so the
// assistant can cite them. Backend: /api/documents, /api/upload,
// /api/training/start, /api/training/status, /api/knowledge/stats.

const KB_MAX_MB = 50;
const KB_ALLOWED = ["txt", "pdf", "png", "jpg", "jpeg", "webp", "gif"];

// ── 索引训练轮询的状态 ─────────────────────────────────────────────────────
// 之前只有一个 kbPollTimer，且每次调用 kbPollTraining() 都无条件再挂一个
// setTimeout —— 打开抽屉、点击训练、抽屉重开各调一次，就是 1 条链变 3 条，
// 每条每 1.5s 发一组请求（状态 + 文档 + 统计），且关掉抽屉也不会停。
// 现在用三个变量把这条链约束成：同一时刻只有一条、有总时长上限、关抽屉即停。
let kbPollTimer = null;      // 当前挂起的定时器
let kbPolling = false;       // 是否已有一条轮询链（含等待下一次定时的那段）
let kbPollDeadline = 0;      // 本链条的绝对截止时间戳（0 = 未开始）
const KB_POLL_INTERVAL_MS = 1500;
const KB_POLL_MAX_MS = 10 * 60 * 1000; // 单次观察最多轮询 10 分钟

/** 停掉轮询链（关抽屉 / 用户重新发起训练时调用）。 */
function kbPollStop() {
  if (kbPollTimer) {
    clearTimeout(kbPollTimer);
    kbPollTimer = null;
  }
  kbPolling = false;
  kbPollDeadline = 0;
}

/** 把训练按钮/进度条恢复成"空闲"态。DOM 缺失时静默跳过。 */
function kbTrainIdle() {
  const bar = document.getElementById("kb-progress");
  const btn = document.getElementById("kb-train");
  const label = document.getElementById("kb-train-label");
  if (bar) bar.hidden = true;
  if (btn) btn.disabled = false;
  if (label) label.textContent = kbT("Start training", "开始训练", "Mula latihan");
}

function kbFormatSize(bytes) {
  if (!bytes && bytes !== 0) return "–";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1024 / 1024).toFixed(1) + " MB";
}

function kbMessage(node, text, kind) {
  if (!node) return;
  if (!text) {
    node.hidden = true;
    node.textContent = "";
    node.className = "kb-msg";
    return;
  }
  node.hidden = false;
  node.textContent = text;
  node.className = "kb-msg" + (kind ? " " + kind : "");
}

async function kbLoadStats() {
  try {
    const res = await fetch("/api/kb/stats", { credentials: "include" });
    if (!res.ok) return;
    const d = await res.json();
    document.getElementById("kb-stat-docs").textContent = d.document_count ?? "–";
    document.getElementById("kb-stat-chunks").textContent = d.total_chunks ?? "–";
    document.getElementById("kb-stat-version").textContent = d.index_version ?? "–";
  } catch (err) {
    /* stats are decorative — ignore */
  }
}

function kbRenderFiles(documents) {
  const box = document.getElementById("kb-files");
  box.textContent = "";
  // Curated sources first, then anything the student added in this session.
  const sorted = documents.slice().sort((a, b) => {
    const ua = a.indexed ? 0 : 1;
    const ub = b.indexed ? 0 : 1;
    if (ua !== ub) return ua - ub;
    return (b.modified || 0) - (a.modified || 0);
  });
  sorted.forEach((doc) => {
    const row = el("div", "kb-file");
    const name = el("span", "kb-file-name", doc.name);
    name.title = doc.name;
    const meta = el("span", "kb-file-meta", kbFormatSize(doc.size));
    const state = el("span", "kb-file-state" + (doc.indexed ? " on" : " off"),
      doc.indexed ? "indexed" : doc.stale ? "stale" : "new");
    // P0-2：只有用户上传（uploads/）的文件显示删除按钮，官方语料不可删
    if (doc.source && doc.source !== "upload") {
      row.appendChild(name);
      row.appendChild(meta);
      row.appendChild(state);
      box.appendChild(row);
      return;
    }
    const del = el("button", "kb-file-del", "✕");
    del.type = "button";
    del.title = "Remove " + doc.name;
    del.addEventListener("click", async () => {
      del.disabled = true;
      try {
        const res = await fetch("/api/documents/" + doc.name.split("/").map(encodeURIComponent).join("/"), {
          method: "DELETE",
          credentials: "include",
        });
        if (!res.ok) throw new Error("HTTP " + res.status);
        kbMessage(document.getElementById("kb-upload-msg"), kbT("Removed " + doc.name, "已删除 " + doc.name, "Dibuang " + doc.name), "ok");
        await kbLoadDocuments();
        await kbLoadStats();
      } catch (err) {
        kbMessage(document.getElementById("kb-upload-msg"), kbT("Could not remove " + doc.name, "删除失败：" + doc.name, "Gagal buang: " + doc.name), "err");
        del.disabled = false;
      }
    });
    row.appendChild(name);
    row.appendChild(meta);
    row.appendChild(state);
    row.appendChild(del);
    box.appendChild(row);
  });
}

async function kbLoadDocuments() {
  const box = document.getElementById("kb-files");
  try {
    const res = await fetch("/api/documents", { credentials: "include" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const d = await res.json();
    kbRenderFiles(d.documents || []);
  } catch (err) {
    box.textContent = "";
    box.appendChild(el("p", "kb-empty", kbT("Could not load the knowledge base.", "知识库加载失败。", "Pangkalan pengetahuan gagal dimuat.")));
  }
}

async function kbUpload(fileList) {
  const msg = document.getElementById("kb-upload-msg");
  const files = Array.from(fileList || []);
  if (!files.length) return;

  const rejected = [];
  const accepted = [];
  files.forEach((f) => {
    const ext = (f.name.split(".").pop() || "").toLowerCase();
    if (!KB_ALLOWED.includes(ext)) rejected.push(f.name + " (unsupported type)");
    else if (f.size > KB_MAX_MB * 1024 * 1024) rejected.push(f.name + " (over 50 MB)");
    else accepted.push(f);
  });
  if (rejected.length) kbMessage(msg, "Skipped: " + rejected.join(", "), "err");
  if (!accepted.length) return;

  kbMessage(msg, kbT("Uploading " + accepted.length + " file(s)…", "正在上传 " + accepted.length + " 个文件…", "Memuat naik " + accepted.length + " fail…"), "");
  const form = new FormData();
  accepted.forEach((f) => form.append("files", f, f.name));
  const btn = document.getElementById("kb-train");
  btn.disabled = true;
  try {
    const res = await fetch("/api/upload", { method: "POST", body: form, credentials: "include" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "HTTP " + res.status);
    const saved = data.saved || [];
    const errs = (data.errors || []).map((e) => (e.name || "file") + ": " + (e.error || "failed"));
    const parts = [];
    if (saved.length) parts.push(kbT("Uploaded " + saved.length + " file(s)", "已上传 " + saved.length + " 个文件", "Berjaya muat naik " + saved.length + " fail"));
    if (errs.length) parts.push(errs.join("; "));
    // 后端会告知这次走的是哪条索引路径：mq = 交给消息队列的索引消费者，
    // local = 本机训练线程兜底（MQ 不可用时），none = 未进入索引。
    // 原实现完全不区分，MQ 挂掉时用户只会看到"已上传"而索引永远不动。
    if (saved.length && data.index_via === "mq") {
      parts.push(kbT("queued for indexing", "已进入索引队列", "dalam baris untuk pengindeksan"));
    } else if (saved.length && data.training_started === false && data.index_via === "local") {
      parts.push(kbT("an indexing run is already in progress", "已有索引任务在运行", "satu proses pengindeksan sedang berjalan"));
    }
    kbMessage(msg, parts.join(" · ") || "Nothing uploaded", errs.length && !saved.length ? "err" : "ok");
    await kbLoadDocuments();
    await kbLoadStats();
    if (data.training_started) {
      // 本机训练已启动 → 直接在面板里显示进度，用户不必手动点"开始训练"
      const bar = document.getElementById("kb-progress");
      const label = document.getElementById("kb-train-label");
      if (bar) bar.hidden = false;
      if (label) label.textContent = kbT("Training…", "训练中…", "Latihan…");
      kbPollTraining();
    }
  } catch (err) {
    kbMessage(msg, kbT("Upload failed: ", "上传失败：", "Muat naik gagal: ") + err.message, "err");
  } finally {
    btn.disabled = false;
    document.getElementById("kb-file").value = "";
  }
}

async function kbStartTraining() {
  const btn = document.getElementById("kb-train");
  const label = document.getElementById("kb-train-label");
  const msg = document.getElementById("kb-train-msg");
  const bar = document.getElementById("kb-progress");
  kbPollStop(); // 用户主动重开一次训练 → 重置轮询链与总时长上限
  btn.disabled = true;
  label.textContent = kbT("Training…", "训练中…", "Latihan…");
  bar.hidden = false;
  kbMessage(msg, kbT("Indexing documents — embedding new chunks, this usually takes under a minute.", "正在索引文档——向量化新片段，通常一分钟内完成。", "Mengindeks dokumen — memvektor cebisan baharu, biasanya selesai dalam masa kurang satu minit."), "");
  try {
    const res = await fetch("/api/training/start", { method: "POST", credentials: "include" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json().catch(() => ({}));
    // 后端已在持锁期间置 running=True，故此处开始轮询必然读到"运行中"，
    // 不会再出现刚提交就误报「训练已停止」的窗口。
    kbPollTraining();
    if (data && data.started === false) {
      kbMessage(msg, kbT("A training run is already in progress — your new files will be picked up when it finishes.", "已有一次训练在运行——新增文件会在它结束后自动接着索引。", "Latihan sudah berjalan — fail baharu anda akan diindeks automatik selepas ia selesai."), "");
    }
  } catch (err) {
    kbMessage(msg, kbT("Could not start training: ", "无法开始训练：", "Gagal mula latihan: ") + err.message, "err");
    kbTrainIdle();
  }
}

/**
 * 训练状态轮询。三条约束（原实现三条全无）：
 *   ① 单链：kbPolling 保证同一时刻只有一条链。原实现每次调用都无条件再挂一个
 *      setTimeout，打开抽屉 + 点训练 + 重开抽屉 = 3 条链并行，每 1.5s 发 3 组请求。
 *   ② 有上限：KB_POLL_MAX_MS 之后放弃，避免训练线程卡死时无限轮询。
 *   ③ 可中断：kbPollStop() 会清掉定时器（抽屉关闭时调用）。
 */
async function kbPollTraining() {
  if (kbPolling) return; // ① 已有一条链在跑，直接忽略这次调用
  kbPolling = true;
  if (!kbPollDeadline) kbPollDeadline = Date.now() + KB_POLL_MAX_MS;

  const msg = document.getElementById("kb-train-msg");
  let continuePolling = false;
  try {
    const res = await fetch("/api/training/status", { credentials: "include" });
    const d = await res.json();
    if (d.running || d.pending) {
      if (Date.now() < kbPollDeadline) {
        continuePolling = true;
      } else {
        kbTrainIdle();
        kbMessage(msg, kbT("Still indexing after 10 minutes — close and reopen this panel to keep watching.", "索引已持续 10 分钟仍未结束——关闭后重新打开面板可继续查看。", "Pengindeksan masih berjalan selepas 10 minit — tutup dan buka semula panel ini untuk terus memantau."), "err");
      }
    } else {
      kbTrainIdle();
      if (d.last_result === "success") {
        kbMessage(msg, kbT("Training finished — the assistant can now use these materials.", "训练完成——助手现在可以使用这些材料了。", "Latihan selesai — pembantu kini boleh menggunakan bahan ini."), "ok");
        setAssistantStatus("Knowledge base updated");
      } else if (d.last_error) {
        kbMessage(msg, kbT("Training failed: ", "训练失败：", "Latihan gagal: ") + d.last_error, "err");
      } else {
        kbMessage(msg, kbT("Training stopped.", "训练已停止。", "Latihan dihentikan."), "");
      }
      await kbLoadDocuments();
      await kbLoadStats();
    }
  } catch (err) {
    kbTrainIdle();
    kbMessage(msg, kbT("Lost connection while training — refresh to check the status.", "训练期间连接中断——刷新页面查看状态。", "Sambungan terputus semasa latihan — muat semula untuk semak status."), "err");
  } finally {
    if (continuePolling) {
      kbPollTimer = setTimeout(() => {
        kbPolling = false; // 先解除守卫，下一次调用才能进入
        kbPollTraining();
      }, KB_POLL_INTERVAL_MS);
    } else {
      kbPollTimer = null;
      kbPolling = false; // 链条结束，允许下次重新开始
      kbPollDeadline = 0;
    }
  }
}

async function kbOpenDrawer() {
  const drawer = document.getElementById("kb-drawer");
  drawer.hidden = false;
  document.body.classList.add("kb-open");
  kbMessage(document.getElementById("kb-upload-msg"), "", "");
  await Promise.all([kbLoadDocuments(), kbLoadStats()]);
  try {
    const res = await fetch("/api/training/status", { credentials: "include" });
    const d = await res.json();
    if (d.running || d.pending) {
      document.getElementById("kb-progress").hidden = false;
      document.getElementById("kb-train").disabled = true;
      document.getElementById("kb-train-label").textContent = "Training…";
      kbPollTraining(); // 幂等：已有链在跑时会被守卫直接忽略
    }
  } catch (err) {
    /* ignore */
  }
}

function kbCloseDrawer() {
  kbPollStop(); // 关抽屉即停止轮询，避免后台无限轮询
  document.getElementById("kb-drawer").hidden = true;
  document.body.classList.remove("kb-open");
}

function kbInit() {
  const openBtn = document.getElementById("sidebar-training");
  if (openBtn) openBtn.addEventListener("click", kbOpenDrawer);
  const closeBtn = document.getElementById("kb-close");
  if (closeBtn) closeBtn.addEventListener("click", kbCloseDrawer);
  const backdrop = document.getElementById("kb-backdrop");
  if (backdrop) backdrop.addEventListener("click", kbCloseDrawer);

  const drop = document.getElementById("kb-drop");
  const input = document.getElementById("kb-file");
  if (drop && input) {
    drop.addEventListener("click", () => input.click());
    drop.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        input.click();
      }
    });
    input.addEventListener("change", () => kbUpload(input.files));
    ["dragenter", "dragover"].forEach((ev) =>
      drop.addEventListener(ev, (e) => {
        e.preventDefault();
        drop.classList.add("over");
      })
    );
    ["dragleave", "drop"].forEach((ev) =>
      drop.addEventListener(ev, (e) => {
        e.preventDefault();
        drop.classList.remove("over");
      })
    );
    drop.addEventListener("drop", (e) => {
      if (e.dataTransfer && e.dataTransfer.files) kbUpload(e.dataTransfer.files);
    });
  }
  const trainBtn = document.getElementById("kb-train");
  if (trainBtn) trainBtn.addEventListener("click", kbStartTraining);
  const refresh = document.getElementById("kb-refresh");
  if (refresh)
    refresh.addEventListener("click", () => {
      kbLoadDocuments();
      kbLoadStats();
    });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      const drawer = document.getElementById("kb-drawer");
      if (drawer && !drawer.hidden) kbCloseDrawer();
    }
  });
}

const BG_STORAGE_KEY = "ftsm_bg_prefs_v1";
const BG_DEFAULTS = {
  bgTheme: "tahoe",
  customColor: "#DCEAFD",
};

const BG_DOT_GRADIENTS = {
  tahoe: "linear-gradient(135deg, #7CC0FF 0%, #B8A4FF 52%, #8CE6DA 100%)",
  aurora: "linear-gradient(135deg, #38BDF8 0%, #8B5CF6 52%, #F472B6 100%)",
  glacier: "linear-gradient(135deg, #22D3EE 0%, #3B82F6 55%, #34D399 100%)",
  sunset: "linear-gradient(135deg, #FB923C 0%, #F472B6 52%, #A78BFA 100%)",
  sakura: "linear-gradient(135deg, #F472B6 0%, #C084FC 55%, #60A5FA 100%)",
  silver: "linear-gradient(135deg, #F8FAFC 0%, #CBD5E1 55%, #94A3B8 100%)",
};

function loadBgPrefs() {
  try {
    const raw = JSON.parse(localStorage.getItem(BG_STORAGE_KEY) || "null");
    if (raw && typeof raw === "object") {
      return {
        bgTheme: typeof raw.bgTheme === "string" ? raw.bgTheme : BG_DEFAULTS.bgTheme,
        customColor: typeof raw.customColor === "string" ? raw.customColor : BG_DEFAULTS.customColor,
      };
    }
  } catch {}
  return { ...BG_DEFAULTS };
}

function saveBgPrefs(prefs) {
  try {
    localStorage.setItem(BG_STORAGE_KEY, JSON.stringify(prefs));
  } catch {}
}

function hexToRgbTuple(hex) {
  const clean = String(hex || "").replace("#", "").trim();
  if (clean.length !== 6) return [220, 234, 253];
  const n = parseInt(clean, 16);
  if (Number.isNaN(n)) return [220, 234, 253];
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function buildCustomWallpaper(hex) {
  const [r, g, b] = hexToRgbTuple(hex);
  const c2r = Math.min(255, Math.round(r * 0.72 + 120 * 0.28));
  const c2g = Math.min(255, Math.round(g * 0.72 + 95 * 0.28));
  const c2b = Math.min(255, Math.round(b * 0.72 + 245 * 0.28));
  const c3r = Math.min(255, Math.round(r * 0.75 + 60 * 0.25));
  const c3g = Math.min(255, Math.round(g * 0.75 + 215 * 0.25));
  const c3b = Math.min(255, Math.round(b * 0.75 + 195 * 0.25));
  const baseTop = `rgb(${Math.min(255, Math.round(r * 0.35 + 255 * 0.65))}, ${Math.min(255, Math.round(g * 0.35 + 255 * 0.65))}, ${Math.min(255, Math.round(b * 0.35 + 255 * 0.65))})`;
  const baseBot = `rgb(${Math.min(255, Math.round(r * 0.52 + 244 * 0.48))}, ${Math.min(255, Math.round(g * 0.52 + 246 * 0.48))}, ${Math.min(255, Math.round(b * 0.52 + 250 * 0.48))})`;
  return {
    base: baseTop,
    wallpaper: [
      `radial-gradient(1080px 740px at 8% -4%, rgba(${r}, ${g}, ${b}, 0.72) 0%, rgba(${r}, ${g}, ${b}, 0) 62%)`,
      `radial-gradient(980px 680px at 92% 14%, rgba(${c2r}, ${c2g}, ${c2b}, 0.52) 0%, rgba(${c2r}, ${c2g}, ${c2b}, 0) 60%)`,
      `radial-gradient(920px 680px at 50% 105%, rgba(${c3r}, ${c3g}, ${c3b}, 0.48) 0%, rgba(${c3r}, ${c3g}, ${c3b}, 0) 62%)`,
      `linear-gradient(180deg, ${baseTop} 0%, ${baseBot} 100%)`,
    ].join(", "),
  };
}

function applyBgPrefs(prefs) {
  const root = document.documentElement;
  if (prefs.bgTheme === "custom") {
    root.setAttribute("data-bg-theme", "custom");
    const custom = buildCustomWallpaper(prefs.customColor);
    root.style.setProperty("--lg-bg-base", custom.base);
    root.style.setProperty("--lg-wallpaper", custom.wallpaper);
  } else {
    root.setAttribute("data-bg-theme", prefs.bgTheme || "tahoe");
    root.style.removeProperty("--lg-bg-base");
    root.style.removeProperty("--lg-wallpaper");
  }

  const dot = document.getElementById("topbar-swatch-dot");
  if (dot) {
    dot.style.background =
      prefs.bgTheme === "custom"
        ? prefs.customColor
        : BG_DOT_GRADIENTS[prefs.bgTheme] || BG_DOT_GRADIENTS.tahoe;
  }

  document.querySelectorAll(".glass-swatch[data-bg-theme]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.bgTheme === prefs.bgTheme);
  });

  const colorInput = document.getElementById("glass-custom-color");
  const colorHex = document.getElementById("glass-custom-hex");
  if (colorInput && prefs.customColor) colorInput.value = prefs.customColor;
  if (colorHex && prefs.customColor) colorHex.textContent = prefs.customColor.toUpperCase();
}

function setupBgCustomizer() {
  let prefs = loadBgPrefs();
  applyBgPrefs(prefs);

  const toggleBtn = document.getElementById("glass-toggle");
  const popover = document.getElementById("glass-popover");
  if (!toggleBtn || !popover) return;

  const setOpen = (open) => {
    popover.hidden = !open;
    toggleBtn.setAttribute("aria-expanded", String(open));
  };

  toggleBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    const langMenu = document.getElementById("lang-menu");
    const langBtn = document.getElementById("lang-toggle");
    if (langMenu && !langMenu.hidden) {
      langMenu.hidden = true;
      if (langBtn) langBtn.setAttribute("aria-expanded", "false");
    }
    setOpen(popover.hidden);
  });

  popover.addEventListener("click", (e) => {
    const swatch = e.target.closest(".glass-swatch[data-bg-theme]");
    if (!swatch) return;
    prefs.bgTheme = swatch.dataset.bgTheme;
    applyBgPrefs(prefs);
    saveBgPrefs(prefs);
  });

  const colorInput = document.getElementById("glass-custom-color");
  if (colorInput) {
    colorInput.addEventListener("input", () => {
      prefs.customColor = colorInput.value;
      prefs.bgTheme = "custom";
      applyBgPrefs(prefs);
      saveBgPrefs(prefs);
    });
  }

  const resetBtn = document.getElementById("glass-reset");
  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      prefs = { ...BG_DEFAULTS };
      applyBgPrefs(prefs);
      saveBgPrefs(prefs);
    });
  }

  document.addEventListener("click", (e) => {
    if (!popover.hidden && !popover.contains(e.target) && !toggleBtn.contains(e.target)) {
      setOpen(false);
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !popover.hidden) setOpen(false);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  kbInit();
  setupBgCustomizer();
  const langBtn = document.getElementById("lang-toggle");
  const langMenu = document.getElementById("lang-menu");
  if (langBtn && langMenu) {
    const setMenu = (open) => {
      langMenu.hidden = !open;
      langBtn.setAttribute("aria-expanded", String(open));
    };
    langBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const glassPop = document.getElementById("glass-popover");
      const glassBtn = document.getElementById("glass-toggle");
      if (glassPop && !glassPop.hidden) {
        glassPop.hidden = true;
        if (glassBtn) glassBtn.setAttribute("aria-expanded", "false");
      }
      setMenu(langMenu.hidden);
    });
    langMenu.addEventListener("click", (e) => {
      const opt = e.target.closest("[data-lang]");
      if (!opt) return;
      setMenu(false);
      applyLang(opt.dataset.lang);
    });
    // 点击菜单外或按 Esc 关闭
    document.addEventListener("click", (e) => {
      if (!langMenu.hidden && !langMenu.contains(e.target) && !langBtn.contains(e.target)) setMenu(false);
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !langMenu.hidden) setMenu(false);
    });
  }
  applyLang(LANG); // 按保存的偏好应用一次（会重渲染各列表）
});

// ── i18n: static-string dictionary + language toggle ────────────────────────

const I18N_ZH = {
  "tab.chat": "聊天",
  "tab.guide": "指南",
  "newchat": "新对话",
  "kb.button": "训练材料",
  "sidebar.recent": "最近对话",
  "composer.ph": "问问签证、巴士、美食……",
  "chat.h1": "今天想问点什么？",
  "chat.sub": "在 UKM FTSM 的签证、巴士、美食、住宿、医疗或课业问题都可以问——回答全部来自官方知识库。",
  "chat.note": "· 签证、费用、截止日期等关键信息请再经 UKM / EMGS 官方渠道核实。",
  "hero.title": "FTSM 学生生活，<br />有问必答。",
  "hero.sub": "签证、巴士、美食、住宿、医疗与课业——内容整理自 UKM 官方渠道，基于知识库生成。",
  "hero.ask": "问一问助手",
  "hero.browse": "浏览指南",
  "stat.docs": "已索引文档",
  "stat.chunks": "知识片段",
  "stat.cache": "缓存回答",
  "stat.status": "助手状态",
  "topics.h": "热门话题",
  "topics.sub": "点击任意问题即可立即向助手提问——页面会自动切到聊天视图。",
  "prog.h": "FTSM 开设项目",
  "prog.sub": "学院官方公示的项目——点击卡片即可向助手询问招生、培养方案和课程。",
  "chk.h": "出发前清单",
  "chk.sub": "边准备边勾选——进度保存在当前浏览器。",
  "chk.reset": "重置清单",
  "hiw.h": "助手是怎么回答的",
  "hiw.sub": "每个回答都经过同一条检索管线——知识库支撑不了的问题会被直接拒答，而不是瞎编。",
  "hiw1.t": "入库",
  "hiw1.d": "FTSM 官方页面、课程表和整理好的指南被爬取、切块并向量化写入索引。",
  "hiw2.t": "混合检索",
  "hiw2.d": "向量检索与 BM25 关键词检索并行执行，再通过倒数排名融合（RRF）合并。",
  "hiw3.t": "重排",
  "hiw3.d": "交叉编码器重排序器把最相关的片段提到最前，再交给模型。",
  "hiw4.t": " grounded 回答",
  "hiw4.d": "模型只依据检索到的上下文作答；证据不足会被双阈值门槛拦下——不产生幻觉回答。",
  "bus.sub": "UKM–KTM 接驳巴士分区路线图。点击地图可放大。",
  "bus.z1": "区域 1", "bus.z2": "区域 2", "bus.z3": "区域 3", "bus.z4": "区域 4",
  "bus.z5": "区域 5", "bus.z6": "区域 6", "bus.z7": "区域 7", "bus.z8": "区域 8",
  "footer": "回答来自 FTSM-RAG 知识库（官方页面、课程表与整理的学生指南）。签证、费用、截止日期等关键信息请再经 UKM / EMGS 官方渠道核实。",
  "story.back": "← 返回指南",
  "story.need": "需要更具体的解答？",
  "story.note": "本页回答由 FTSM-RAG 知识库生成（UKM 官方页面、课程表与整理的学生指南）。签证、费用、截止日期等关键信息请再经 UKM / EMGS 官方渠道核实。",
  "kb.h": "训练材料",
  "kb.sub": "上传自己的笔记或文档，然后重建索引，助手就能引用它们回答。",
  "kb.drop": "<strong>把文件拖到这里</strong>，或点击选择",
  "kb.hint": "TXT / PDF / PNG / JPG · 单个不超过 50 MB",
  "kb.section": "知识库文件",
  "kb.refresh": "刷新",
  "kb.train": "开始训练",
  "kb.documents": "个文档",
  "kb.chunks": "个片段",
  "kb.indexv": "索引版本",
  "glass.bg.btn": "背景色",
  "glass.bg": "背景主题色",
  "glass.reset": "恢复默认",
  "glass.bg.tahoe": "天青",
  "glass.bg.aurora": "极光",
  "glass.bg.glacier": "冰川",
  "glass.bg.sunset": "暮霞",
  "glass.bg.sakura": "樱粉",
  "glass.bg.silver": "银雾",
  "glass.bg.custom": "自定义色调",
};

const I18N_MS = {
  "tab.chat": "Sembang",
  "tab.guide": "Panduan",
  "newchat": "Perbualan baharu",
  "kb.button": "Bahan latihan",
  "sidebar.recent": "Perbualan terkini",
  "composer.ph": "Tanya tentang visa, bas, makanan……",
  "chat.h1": "Ada soalan hari ini?",
  "chat.sub": "Soalan tentang visa, bas, makanan, penginapan, kesihatan atau pengajian di UKM FTSM — semua jawapan datang daripada pangkalan pengetahuan rasmi.",
  "chat.note": "· Sila sahkan maklumat penting seperti visa, yuran dan tarikh akhir melalui saluran rasmi UKM / EMGS.",
  "hero.title": "Kehidupan pelajar FTSM,<br />semua soalan dijawab.",
  "hero.sub": "Visa, bas, makanan, penginapan, kesihatan dan pengajian — disusun daripada saluran rasmi UKM, dijana berdasarkan pangkalan pengetahuan.",
  "hero.ask": "Tanya pembantu",
  "hero.browse": "Layari panduan",
  "stat.docs": "Dokumen diindeks",
  "stat.chunks": "Cebisan pengetahuan",
  "stat.cache": "Jawapan cache",
  "stat.status": "Status pembantu",
  "topics.h": "Topik popular",
  "topics.sub": "Klik mana-mana soalan untuk terus bertanya — halaman akan bertukar ke paparan sembang secara automatik.",
  "prog.h": "Program yang ditawarkan FTSM",
  "prog.sub": "Program rasmi fakulti — klik kad untuk bertanya tentang kemasukan, pelan pengajian dan kursus.",
  "chk.h": "Senarai semak sebelum berlepas",
  "chk.sub": "Tandakan sambil bersedia — kemajuan disimpan dalam pelayar ini.",
  "chk.reset": "Set semula senarai",
  "hiw.h": "Bagaimana pembantu menjawab",
  "hiw.sub": "Setiap jawapan melalui saluran carian yang sama — soalan yang tidak disokong pangkalan pengetahuan akan ditolak, bukan dijawab secara teragak-agak.",
  "hiw1.t": "Ingestan",
  "hiw1.d": "Laman rasmi FTSM, jadual waktu dan panduan pelajar yang tersusun dikikis, dipecah kepada cebisan dan divektorkan ke dalam indeks.",
  "hiw2.t": "Carian hibrid",
  "hiw2.d": "Carian vektor dan carian kata kunci BM25 dijalankan serentak, kemudian digabungkan melalui Reciprocal Rank Fusion (RRF).",
  "hiw3.t": "Susun semula",
  "hiw3.d": "Penyusun semula silang-pengekod menaikkan cebisan paling berkaitan ke hadapan sebelum diserahkan kepada model.",
  "hiw4.t": "Jawapan berasas sumber",
  "hiw4.d": "Model hanya menjawab berdasarkan konteks yang dikesan; kekurangan bukti akan disekat oleh ambang berganda — tiada jawapan halusinasi.",
  "bus.sub": "Peta laluan zon bas penghubung UKM–KTM. Klik peta untuk zum.",
  "bus.z1": "Zon 1", "bus.z2": "Zon 2", "bus.z3": "Zon 3", "bus.z4": "Zon 4",
  "bus.z5": "Zon 5", "bus.z6": "Zon 6", "bus.z7": "Zon 7", "bus.z8": "Zon 8",
  "footer": "Jawapan datang daripada pangkalan pengetahuan FTSM-RAG (laman rasmi, jadual waktu dan panduan pelajar yang tersusun). Sila sahkan maklumat penting seperti visa, yuran dan tarikh akhir melalui saluran rasmi UKM / EMGS.",
  "story.back": "← Kembali ke panduan",
  "story.need": "Perlu jawapan yang lebih khusus?",
  "story.note": "Halaman ini dijana oleh pangkalan pengetahuan FTSM-RAG (laman rasmi UKM, jadual waktu dan panduan pelajar). Sila sahkan maklumat penting seperti visa, yuran dan tarikh akhir melalui saluran rasmi UKM / EMGS.",
  "kb.h": "Bahan latihan",
  "kb.sub": "Muat naik nota atau dokumen anda sendiri, kemudian bina semula indeks — pembantu boleh merujuknya ketika menjawab.",
  "kb.drop": "<strong>Seret fail ke sini</strong>, atau klik untuk pilih",
  "kb.hint": "TXT / PDF / PNG / JPG · maksimum 50 MB setiap satu",
  "kb.section": "Fail pangkalan pengetahuan",
  "kb.refresh": "Muat semula",
  "kb.train": "Mula latihan",
  "kb.documents": "dokumen",
  "kb.chunks": "cebisan",
  "kb.indexv": "Versi indeks",
  "glass.bg.btn": "Tema",
  "glass.bg": "Warna Latar",
  "glass.reset": "Set semula",
  "glass.bg.tahoe": "Tahoe",
  "glass.bg.aurora": "Aurora",
  "glass.bg.glacier": "Glasier",
  "glass.bg.sunset": "Senja",
  "glass.bg.sakura": "Sakura",
  "glass.bg.silver": "Perak",
  "glass.bg.custom": "Warna suai",
};

function applyLang(lang) {
  LANG = lang === "zh" || lang === "ms" ? lang : "en";
  try { localStorage.setItem("ftsm_lang", LANG); } catch {}
  const dict = LANG === "zh" ? I18N_ZH : LANG === "ms" ? I18N_MS : null;
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    const key = node.getAttribute("data-i18n");
    if (key === null) return;
    if (node.dataset.i18nEn === undefined) node.dataset.i18nEn = node.innerHTML;
    if (dict && dict[key] !== undefined) node.innerHTML = dict[key];
    else node.innerHTML = node.dataset.i18nEn;
  });
  document.querySelectorAll("[data-i18n-ph]").forEach((node) => {
    const key = node.getAttribute("data-i18n-ph");
    if (node.dataset.i18nPhEn === undefined) node.dataset.i18nPhEn = node.placeholder || "";
    if (dict && dict[key] !== undefined) node.placeholder = dict[key];
    else node.placeholder = node.dataset.i18nPhEn;
  });
  const toggle = document.getElementById("lang-toggle");
  // 下拉模式：按钮显示【当前】语言名，菜单里同步勾选高亮
  if (toggle) toggle.textContent = LANG === "en" ? "English" : LANG === "zh" ? "中文" : "Bahasa Melayu";
  const langMenu = document.getElementById("lang-menu");
  if (langMenu)
    langMenu.querySelectorAll("[data-lang]").forEach((opt) =>
      opt.classList.toggle("active", opt.dataset.lang === LANG)
    );
  document.documentElement.lang = LANG === "zh" ? "zh-CN" : LANG === "ms" ? "ms" : "en";
  renderCards();
  renderProgrammes();
  renderChecklist();
  renderSuggestions();
  renderTrending();
}

// Pick the localized field of a data object: obj.<base> with _zh/_ms suffix fallback.
function pickL(obj, base) {
  if (LANG === "zh" && obj[base + "_zh"]) return obj[base + "_zh"];
  if (LANG === "ms" && obj[base + "_ms"]) return obj[base + "_ms"];
  return obj[base];
}

// Inline trilingual string helper.
function t3(en, zh, ms) {
  return LANG === "zh" ? zh : LANG === "ms" ? ms : en;
}

function kbT(en, zh, ms) {
  return LANG === "zh" ? zh : LANG === "ms" ? (ms !== undefined ? ms : en) : en;
}

// 抽屉里的动态消息本地化（替换 KB 模块里的固定英文串）
const _kbOrigRenderFiles = kbRenderFiles;
kbRenderFiles = function (documents) {
  _kbOrigRenderFiles(documents);
  const stateMap = LANG === "zh"
    ? { indexed: "已索引", new: "新增", stale: "待更新" }
    : LANG === "ms"
    ? { indexed: "Telah diindeks", new: "Baharu", stale: "Perlu dikemas kini" }
    : null;
  if (stateMap) {
    document.querySelectorAll(".kb-file-state").forEach((node) => {
      if (stateMap[node.textContent.trim()]) node.textContent = stateMap[node.textContent.trim()];
    });
  }
};
