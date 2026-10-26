import pw from "/Users/houzhengbo/.workbuddy/binaries/node/workspace/node_modules/playwright-core/index.js";
const { chromium } = pw;
import fs from "node:fs";

const PROJ = "/Users/houzhengbo/Desktop/PHILIPS资料/学习工作/RAG项目/FTSM-RAG";
const OUT = PROJ + "/docs/sidebar-v5-shots";
const BK_CSS = PROJ + "/_backup-liquidglass-20261016-sidebar/guide.css";
const BK_HTML = PROJ + "/_backup-liquidglass-20261016-sidebar/guide.html";
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const URL = "http://127.0.0.1:8080/guide";

const fixture = JSON.parse(fs.readFileSync("/tmp/conv-fixture.json", "utf8"));
fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({
  executablePath: CHROME,
  headless: true,
  args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--force-color-profile=srgb"],
});

const GLASS_FN_SRC = "topbar|chat-sidebar|composer|kb-panel|kb-drawer-backdrop";

async function audit(page) {
  return page.evaluate((src) => {
    const re = new RegExp(src);
    const hits = [];
    for (const el of document.querySelectorAll("*")) {
      const vis = el.checkVisibility ? el.checkVisibility() : !!(el.offsetWidth || el.offsetHeight);
      if (!vis) continue;
      const cs = getComputedStyle(el);
      if (cs.backdropFilter && cs.backdropFilter !== "none") {
        const cls = typeof el.className === "string" ? el.className.trim().split(/\s+/).join(".") : "";
        hits.push({ key: el.tagName.toLowerCase() + (cls ? "." + cls : ""), filter: cs.backdropFilter, functional: re.test(cls) });
      }
    }
    return hits;
  }, GLASS_FN_SRC);
}

async function seed(page) {
  // force the first row to render as "active" through the REAL renderer
  const ok = await page.evaluate(() => {
    try {
      if (typeof ASSISTANT === "object" && Array.isArray(HISTORY.items) && HISTORY.items[0]) {
        ASSISTANT.conversationId = HISTORY.items[0].id;
        renderHistoryList();
        return true;
      }
    } catch (e) { /* fall through */ }
    const r = document.querySelector(".sidebar-item");
    if (r) { r.classList.add("active"); return "dom"; }
    return false;
  });
  return ok;
}

const MEASURE = () => {
  const g = (sel, props) => {
    const el = document.querySelector(sel);
    if (!el) return { sel, missing: true };
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    const o = { sel, w: +r.width.toFixed(1), h: +r.height.toFixed(1) };
    for (const p of props) o[p] = cs[p];
    return o;
  };
  const LAB = ["fontSize", "fontWeight", "color", "backgroundColor", "borderRadius", "letterSpacing", "textTransform", "display", "justifyContent", "paddingLeft"];
  return {
    row: g(".sidebar-item", ["flexDirection", "alignItems", "minHeight", "height", "borderRadius", "paddingLeft", "gap", "backgroundImage"]),
    title: g(".sidebar-item-title", ["fontSize", "fontWeight", "color", "flexGrow", "minWidth", "textOverflow", "whiteSpace"]),
    time: g(".sidebar-item-time", ["fontSize", "color", "position", "fontVariantNumeric", "opacity", "flexGrow"]),
    activeRow: g(".sidebar-item.active", ["backgroundColor"]),
    activeTitle: g(".sidebar-item.active .sidebar-item-title", ["color", "fontWeight"]),
    activeTime: g(".sidebar-item.active .sidebar-item-time", ["color"]),
    activeDel: g(".sidebar-item.active .sidebar-item-del", ["color", "width", "height", "borderRadius", "opacity", "position", "right", "top"]),
    newchat: g("#sidebar-newchat", LAB),
    action: g("#sidebar-training", LAB),
    label: g(".sidebar-label", ["fontSize", "fontWeight", "color", "letterSpacing", "textTransform", "marginTop"]),
    rowCount: document.querySelectorAll(".sidebar-item").length,
  };
};

// ── run one context, mode = "before" | "after" ────────────────────────
async function run(mode) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  await ctx.route("**/api/conversations", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: fixture }) })
  );
  if (mode === "before") {
    await ctx.route("**/static/guide.css*", (r) => r.fulfill({ path: BK_CSS, contentType: "text/css" }));
    await ctx.route("**/guide", (r) =>
      r.request().resourceType() === "document" ? r.fulfill({ path: BK_HTML, contentType: "text/html" }) : r.continue()
    );
  }
  const page = await ctx.newPage();
  const errs = [];
  page.on("pageerror", (e) => errs.push(String(e).slice(0, 120)));
  await page.goto(URL, { waitUntil: "networkidle" }).catch(() => {});
  await page.waitForSelector(".sidebar-item", { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(900);
  const seeded = await seed(page);
  await page.waitForTimeout(350);
  console.log(`\n===== ${mode.toUpperCase()} =====  seeded=${seeded}  pageerrors=${errs.length}${errs.length ? " :: " + errs.join(" | ") : ""}`);

  const glass = await audit(page);
  console.log("glass:", JSON.stringify(glass));
  console.log("content-layer violations:", glass.filter((x) => !x.functional).length);

  console.log("metrics:", JSON.stringify(await page.evaluate(MEASURE), null, 1));

  await page.locator(".chat-sidebar").screenshot({ path: `${OUT}/${mode === "before" ? "01-before" : "02-after"}-sidebar.png` });

  if (mode === "after") {
    // hover a NON-active row → time fades out, × fades in
    const idle = page.locator(".sidebar-item:not(.active)").first();
    if (await idle.count()) {
      await idle.hover();
      await page.waitForTimeout(500);
      await page.locator(".chat-sidebar").screenshot({ path: `${OUT}/03-after-sidebar-hover.png` });
      console.log("hover:", JSON.stringify(await page.evaluate(() => {
        const row = document.querySelector(".sidebar-item:not(.active)");
        const t = row.querySelector(".sidebar-item-time"), d = row.querySelector(".sidebar-item-del");
        return { timeOpacity: getComputedStyle(t).opacity, delOpacity: getComputedStyle(d).opacity, delColor: getComputedStyle(d).color, delBg: getComputedStyle(d).backgroundColor };
      })));
    }
    // hover the ACTIVE row → × on blue
    const act = page.locator(".sidebar-item.active");
    if (await act.count()) {
      await act.hover();
      await page.waitForTimeout(500);
      await page.locator(".chat-sidebar").screenshot({ path: `${OUT}/04-after-sidebar-active-hover.png` });
    }
    await page.locator(".topbar-right").hover().catch(() => {});
    await page.waitForTimeout(200);
    const tr = page.locator(".topbar-right");
    if (await tr.count()) await tr.screenshot({ path: `${OUT}/05-after-topbar-right.png` });
    await page.screenshot({ path: `${OUT}/06-after-chat-full.png` });
  }
  await ctx.close();
}

await run("before");
await run("after");
await browser.close();
console.log("\ndone →", OUT);
