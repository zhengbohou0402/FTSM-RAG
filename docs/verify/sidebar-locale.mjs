import pw from "/Users/houzhengbo/.workbuddy/binaries/node/workspace/node_modules/playwright-core/index.js";
const { chromium } = pw;
import fs from "node:fs";

const OUT = "/Users/houzhengbo/Desktop/PHILIPS资料/学习工作/RAG项目/FTSM-RAG/docs/sidebar-v5-shots";
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const fixture = JSON.parse(fs.readFileSync("/tmp/conv-fixture.json", "utf8"));

const browser = await chromium.launch({
  executablePath: CHROME, headless: true,
  args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
});

for (const lang of ["en", "zh"]) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  await ctx.route("**/api/conversations", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: fixture }) })
  );
  const page = await ctx.newPage();
  await page.addInitScript((l) => { try { localStorage.setItem("ftsm_lang", l); } catch (e) {} }, lang);
  await page.goto("http://127.0.0.1:8080/guide", { waitUntil: "networkidle" }).catch(() => {});
  await page.waitForSelector(".sidebar-item", { timeout: 15000 }).catch(() => {});
  await page.evaluate(() => { try { ASSISTANT.conversationId = HISTORY.items[0].id; renderHistoryList(); } catch (e) {} });
  await page.waitForTimeout(600);

  const info = await page.evaluate(() => {
    const q = (s) => document.querySelector(s);
    const txt = (s) => (q(s) ? q(s).textContent.trim() : null);
    const svgCount = (s) => (q(s) ? q(s).querySelectorAll("svg").length : -1);
    return {
      sidebarNewchatText: txt("#sidebar-newchat"),
      sidebarNewchatSvg: svgCount("#sidebar-newchat"),
      sidebarActionText: txt("#sidebar-training"),
      sidebarActionSvg: svgCount("#sidebar-training"),
      topbarNewchatText: txt("#assistant-new-chat"),
      topbarNewchatSvg: svgCount("#assistant-new-chat"),
      label: txt(".sidebar-label"),
      langToggle: txt("#lang-toggle"),
      // any fullwidth plus left anywhere on screen?
      fullwidthPlusInSidebar: /＋/.test(q(".chat-sidebar").textContent),
      sidebarNewchatWidth: +q("#sidebar-newchat").getBoundingClientRect().width.toFixed(1),
      sidebarNewchatHeight: +q("#sidebar-newchat").getBoundingClientRect().height.toFixed(1),
    };
  });
  console.log(`[${lang}]`, JSON.stringify(info));
  await page.locator(".chat-sidebar").screenshot({ path: `${OUT}/07-locale-${lang}-sidebar.png` });
  await ctx.close();
}
await browser.close();
console.log("locale check done");
