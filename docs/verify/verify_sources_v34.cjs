// Verify §12 v3.4 Perplexity-style sources block (FTSM-RAG /guide).
// Usage: NODE_PATH=<workspace>/node_modules node verify_sources_v34.cjs
const path = require("path");
const { chromium } = require("playwright-core");

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const BASE = "http://127.0.0.1:8080";
const OUT = path.resolve(__dirname, "../liquid-glass-v3-shots");

const SAMPLE = [
  "根据课程资料，RAG 检索链路由三部分组成：向量召回、重排与引用生成。",
  "",
  "- **向量召回**：Qdrant top-k 检索，附带分数门限",
  "- **重排**：交叉编码器对候选块二次打分",
  "- **引用生成**：答案末尾附 Sources 列表，前端渲染为来源卡片",
  "",
  "Sources:",
  "- [1] lecture04-rag-pipeline.pdf (Chunk 3)",
  "- [2] ftsm-timetable-2026.pdf (Chunk 1)",
  "- [3] coursework-brief.pdf (Chunk 7)",
  "- [4] grading-rubric.pdf (Chunk 2)",
  "- [5] lab-manual-week5.pdf (Chunk 4)",
  "- [6] reading-list.pdf (Chunk 9)",
].join("\n");

(async () => {
  const browser = await chromium.launch({
    executablePath: CHROME,
    args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
  });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  page.on("pageerror", (e) => console.log("PAGEERROR:", e.message));
  await page.goto(BASE + "/guide", { waitUntil: "networkidle" });

  // Make sure the chat view is the visible one.
  const chatHidden = await page.$eval("#view-chat", (el) => el.hidden);
  if (chatHidden) {
    await page.click('.topbar-tab:has-text("Chat")');
  }

  // Inject a bot message rendered by the REAL renderAnswer().
  const info = await page.evaluate((sample) => {
    const thread = document.querySelector(".chat-thread");
    if (!thread) throw new Error(".chat-thread not found");
    const msg = document.createElement("div");
    msg.className = "chat-msg bot markdown";
    msg.innerHTML = window.renderAnswer ? renderAnswer(sample) : "NO renderAnswer";
    thread.appendChild(msg);
    return { hasFn: typeof renderAnswer === "function" };
  }, SAMPLE);
  console.log("renderAnswer available:", info.hasFn);

  const m = await page.evaluate(() => {
    const gs = (sel, prop) => {
      const el = document.querySelector(sel);
      return el ? getComputedStyle(el)[prop] : "MISSING";
    };
    const rect = (sel) => {
      const el = document.querySelector(sel);
      if (!el) return "MISSING";
      const r = el.getBoundingClientRect();
      return { x: +r.x.toFixed(1), y: +r.y.toFixed(1), w: +r.width.toFixed(1), h: +r.height.toFixed(1) };
    };
    const list = document.querySelector(".source-list");
    return {
      // DOM order: sources-block must come BEFORE the first <p> of the answer
      order: (() => {
        const block = document.querySelector(".chat-msg.bot .sources-block");
        const p = document.querySelector(".chat-msg.bot > p");
        return block && p ? (block.compareDocumentPosition(p) & Node.DOCUMENT_POSITION_FOLLOWING ? "sources-first" : "text-first") : "n/a";
      })(),
      block_border: gs(".sources-block", "borderTopWidth") + " " + gs(".sources-block", "borderTopColor"),
      block_bg: gs(".sources-block", "backgroundColor"),
      head_case: gs(".sources-head", "textTransform"),
      head_size: gs(".sources-head", "fontSize"),
      head_svg: gs(".sources-head svg", "display"),
      list_dir: gs(".source-list", "flexDirection"),
      list_overflow: gs(".source-list", "overflowX"),
      list_scrollable: list ? list.scrollWidth + ">" + list.clientWidth : "n/a",
      item_flex: gs(".source-item", "flexBasis") + " / " + gs(".source-item", "flexDirection"),
      item_radius: gs(".source-item", "borderRadius"),
      item_bg: gs(".source-item", "backgroundColor"),
      num_bg: gs(".source-num", "backgroundColor"),
      num_color: gs(".source-num", "color"),
      name_clamp: gs(".source-name", "webkitLineClamp"),
      name_ws: gs(".source-name", "whiteSpace"),
      desc_color: gs(".source-desc", "color"),
      count_bg: gs(".sources-count", "backgroundColor"),
      item_rect: rect(".source-item"),
      n_tiles: document.querySelectorAll(".source-item").length,
    };
  });
  console.log(JSON.stringify(m, null, 2));

  // Hover first tile → number badge should turn accent blue.
  await page.hover(".source-item:first-child");
  await page.waitForTimeout(250);
  const hover = await page.evaluate(() => {
    const el = document.querySelector(".source-item:first-child .source-num");
    const s = getComputedStyle(el);
    return { num_bg_hover: s.backgroundColor, num_color_hover: s.color, item_bg_hover: getComputedStyle(el.parentElement).backgroundColor };
  });
  console.log("HOVER:", JSON.stringify(hover));

  // Screenshots: whole viewport + close-up of the sources row.
  await page.mouse.move(0, 0); // clear hover for the clean shot
  await page.waitForTimeout(200);
  await page.screenshot({ path: path.join(OUT, "12-sources-perplexity.png") });
  const block = await page.$(".chat-msg.bot .sources-block");
  if (block) await block.screenshot({ path: path.join(OUT, "12-sources-closeup.png") });

  await browser.close();
  console.log("DONE");
})().catch((e) => { console.error("FAIL:", e); process.exit(1); });
