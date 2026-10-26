import pw from "/Users/houzhengbo/.workbuddy/binaries/node/workspace/node_modules/playwright-core/index.js";
const { chromium } = pw;
import fs from "node:fs";

const PROJ = "/Users/houzhengbo/Desktop/PHILIPS资料/学习工作/RAG项目/FTSM-RAG";
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const fixture = JSON.parse(fs.readFileSync("/tmp/conv-fixture.json", "utf8"));

const browser = await chromium.launch({
  executablePath: CHROME, headless: true,
  args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
});
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
await ctx.route("**/api/conversations", (r) =>
  r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: fixture }) })
);
const page = await ctx.newPage();
await page.goto("http://127.0.0.1:8080/guide", { waitUntil: "networkidle" }).catch(() => {});
await page.waitForSelector(".sidebar-item", { timeout: 15000 }).catch(() => {});
await page.evaluate(() => { try { ASSISTANT.conversationId = HISTORY.items[0].id; renderHistoryList(); } catch (e) {} });
await page.waitForTimeout(400);

const out = await page.evaluate(() => {
  const sb = document.querySelector(".chat-sidebar");
  const base = sb.getBoundingClientRect().left;
  const X = (el) => (el ? +(el.getBoundingClientRect().left - base).toFixed(1) : null);
  const txtX = (el) => {
    if (!el) return null;
    const r = document.createRange();
    r.selectNodeContents(el);
    const rects = r.getClientRects();
    return rects.length ? +(rects[0].left - base).toFixed(1) : null;
  };
  const sbCS = getComputedStyle(sb);
  return {
    sidebarPaddingLeft: sbCS.paddingLeft,
    grid: {
      newchatBox: X(document.querySelector("#sidebar-newchat")),
      newchatIcon: X(document.querySelector("#sidebar-newchat .sidebar-ico")),
      newchatText: txtX(document.querySelector("#sidebar-newchat span")),
      actionBox: X(document.querySelector("#sidebar-training")),
      actionIcon: X(document.querySelector("#sidebar-training .sidebar-ico")),
      actionText: txtX(document.querySelector("#sidebar-training span")),
      labelBox: X(document.querySelector(".sidebar-label")),
      labelText: txtX(document.querySelector(".sidebar-label")),
      rowBox: X(document.querySelector(".sidebar-item")),
      rowTitleText: txtX(document.querySelector(".sidebar-item-title")),
    },
    heights: {
      newchat: +document.querySelector("#sidebar-newchat").getBoundingClientRect().height.toFixed(1),
      action: +document.querySelector("#sidebar-training").getBoundingClientRect().height.toFixed(1),
      row: +document.querySelector(".sidebar-item").getBoundingClientRect().height.toFixed(1),
      label: +document.querySelector(".sidebar-label").getBoundingClientRect().height.toFixed(1),
      listRows: document.querySelectorAll(".sidebar-item").length,
      listTop: +(document.querySelector(".sidebar-list").getBoundingClientRect().top - sb.getBoundingClientRect().top).toFixed(1),
      listBottom: +(document.querySelector(".sidebar-list").getBoundingClientRect().bottom - sb.getBoundingClientRect().top).toFixed(1),
    },
    titleSpace: {
      titleContentWidth: +document.querySelector(".sidebar-item-title").getBoundingClientRect().width.toFixed(1),
      timeWidth: +document.querySelector(".sidebar-item-time").getBoundingClientRect().width.toFixed(1),
    },
    del: (() => {
      const d = document.querySelector(".sidebar-item-del");
      return { color: getComputedStyle(d).color, fontSize: getComputedStyle(d).fontSize };
    })(),
  };
});
console.log(JSON.stringify(out, null, 1));
await browser.close();
