# Liquid Glass 主题 · 换模型交接提示词（v3.2 基线）

> 用法：把下面分隔线以内的**全部内容**复制给新模型。图片可选（主页 + 聊天页 + 训练抽屉打开态）。
> 基线版本：`guide.css?v=20261015h`。生成于 2026-10-15。

---

## 角色

你同时是：
1. **Apple 人机界面设计审查专家** —— 精通 Apple HIG（尤其 *Materials* 章节）与 macOS Tahoe / iOS 26 的 Liquid Glass 材质语言；
2. **资深前端工程师** —— 精通 CSS `backdrop-filter`、层叠上下文 / Backdrop Root、合成层性能、渐进降级。

## 项目

FTSM 校园问答助手，纯 HTML/CSS/JS 前端，浅色主题，中英混排界面，品牌色 teal。我用纯 CSS 实现了一套 "Apple Liquid Glass" 主题，需要你审查它是否真的达到 Apple 的设计语言，并给出**可直接粘贴落地**的 CSS。

**关键路径**
```
项目根      /Users/houzhengbo/Desktop/Desktop - 侯政博的MacBook Pro/PHILIPS资料/学习工作/RAG项目/FTSM-RAG
主题 CSS    web/static/guide.css     ← 主题层在文件末尾，搜 "Apple Liquid Glass theme v3"
页面模板    web/templates/guide.html ← 第 14 行有 <link ... guide.css?v=YYYYMMDDx>
已有文档    docs/LIQUID_GLASS_V2_REVIEW.md   ← 前几轮审查报告，含官方原文对照，先读
             docs/liquid-glass-v3.patch.css  ← 当前已应用的主题层（与线上同步）
             docs/liquid-glass-v3-shots/     ← 实测截图
```

**启动方式（重要）**
- 后端是 **Docker 容器模式**，容器 `ftsm-stack` 已映射 8080 + 8101~8104，通常已在运行。
- 前端页面：**http://127.0.0.1:8080/guide**（默认进 Chat 视图；`/` 是旧版 legacy 页面，别看那个）。
- **不要执行 `scripts/stack_up.sh`** —— 那是 host 模式，会 `pkill` 现有进程再起 5 个 Java/Python 进程，跟容器抢端口。
- 改完 CSS **必须同时升 `guide.html` 里的 `?v=` 版本号**，否则浏览器走缓存，你会误判"改了没生效"。

## 硬约束（违反即不合格）

1. **只能改 CSS**（含伪元素 `::before`/`::after`），不能改 HTML / JS。
2. **每条结论必须有证据**：要么是读代码的实测值（`getComputedStyle` / `getBoundingClientRect`），要么是官方原文引用。**禁止凭同类项目经验猜测。**
3. 没有证据支持的判断必须显式标注 **【推断】**，并说明需要什么证据才能确认。
4. 不接受"应该可以"式伪代码。给的代码必须是完整选择器 + 完整属性值，可整段粘贴。
5. 涉及删除/覆盖既有文件时先给备份方案。

## 当前已落地的事实（基线，读代码可复核）

**材质分层**（已按 HIG 原文 *"Don't use Liquid Glass in the content layer"* 收敛）

| 层 | 选择器 | 材质 |
|---|---|---|
| 导航/控件层（Liquid Glass, regular） | `.topbar` 30px · `.chat-sidebar` 30px · `.composer` 36px · `.kb-panel` 48px | `blur() saturate() brightness(1.06)` + 渐变折射边 + 左上镜面高光 |
| 内容层（standard material） | `.oai-card` / `.oai-hero-banner` / `.story-hero` | `backdrop-filter: none`，`rgba(255,255,255,0.88)` + hairline |

**其他已修**：15 处硬编码浅灰（2.2~3.0:1）提到 `--tx-3 #4a5453`（6.6~7.6:1）；嵌套/无效 `backdrop-filter` 全部撤除；`prefers-reduced-motion` / `prefers-reduced-transparency` / `prefers-contrast` / `@supports not` 回退；`:focus-visible` 2px teal outline；卡片 hover 特异性 bug；顶栏与侧栏 L 形连续玻璃（顶栏分段 gradient，0~252px 与侧栏同 fill）；工具栏按钮无边框化；同心圆角 卡 28 / 缩略图 14。

## ⚠️ 已踩过的坑（别再踩）

1. **`.oai-section:not(.oai-section-gray) .oai-card` 是 (0,3,0)** —— 这个文件里卡样式改不动，八成是被它压住。要覆盖必须**等特异性 + 更靠后**（`:where()` 会降到 (0,1,0)，反而更输）。
2. **页面是 app shell，不是文档滚动** —— `body.chat-page` 是 `height:100vh + overflow:hidden`，`document.scrollHeight === clientHeight`。所以 `position: sticky` **完全无效**。真正滚动的是 `#view-guide` / `#view-topic`（自身 `overflow-y:auto`）；`#view-chat` 不滚动。三个视图用 **`hidden` 属性**切换，所以可以用 `:has(#view-guide:not([hidden]))` 精确命中。
3. **同心圆角基数不是 22** —— 无缩略图的卡 padding 22，但带缩略图的走 `.oai-card.has-media { padding: 14px 14px 18px }`。同心半径 = 父半径 − **14**。
4. **macOS 工具链坑**：BSD `grep "a\|b"` 静默返回空，交替匹配**必须 `grep -E`**；`sed -i ''` 在 zsh 下会把表达式当文件名，改用 Python 改文件。
5. **`ps` 在沙箱里被禁**，只能靠 curl 探端口判断服务状态。
6. **看不到图时怎么验证**：用 `getComputedStyle` / `getBoundingClientRect` 做量化断言，比截图可靠。下面有现成脚手架。

## 验证脚手架（直接可用）

```bash
cat > /tmp/check.js <<'EOF'
const { chromium } = require('playwright-core');
(async () => {
  const b = await chromium.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    args: ['--no-sandbox','--disable-gpu','--disable-dev-shm-usage']
  });
  const p = await b.newPage({ viewport:{width:1440,height:900}, deviceScaleFactor:2 });
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto('http://127.0.0.1:8080/guide', { waitUntil:'networkidle' });
  await p.waitForTimeout(1200);
  // 切到 Guide 视图：点第二个 tab
  await p.evaluate(() => { [...document.querySelectorAll('.topbar-tabs a,.topbar-tabs button')][1].click(); });
  await p.waitForTimeout(1000);
  console.log(await p.evaluate(() => {
    const g = s => { const e=document.querySelector(s); if(!e) return 'n/a';
      const cs=getComputedStyle(e); return cs.backdropFilter || cs.webkitBackdropFilter || 'none'; };
    return JSON.stringify({ topbar:g('.topbar'), sidebar:g('.chat-sidebar'),
      composer:g('.composer'), card:g('.oai-card') });
  }));
  console.log('ERR', JSON.stringify(errs.slice(0,4)));
  await b.close();
})();
EOF
NODE_PATH=/Users/houzhengbo/.workbuddy/binaries/node/workspace/node_modules \
  /Users/houzhengbo/.workbuddy/binaries/node/versions/24.14.0/bin/node /tmp/check.js
```
开启抽屉：`document.getElementById('kb-drawer').hidden=false; document.body.classList.add('kb-open');`

**官方依据**（审查请引用 verbatim，不要凭记忆）
- https://developer.apple.com/design/human-interface-guidelines/materials
- WWDC25《Meet Liquid Glass》(219) — Principles 章节
- WWDC25《Get to know the new design system》(356) — Design Language 章节

## 建议优先审的方向（选一个，不要一次全做）

- **A. Scroll Edge Effects**：官方说内容滚到栏下应"溶解"。CSS 无滚动位置查询，静态 mask 会误伤静止首屏。请评估是否值得上 `animation-timeline: scroll()`，并给可回滚方案。
- **B. 暗色模式**：把现有令牌重构成 `prefers-color-scheme: dark` 覆盖层（暗色下 `brightness` 要 <1、`saturate` 要降、投影要让位给描边）。
- **C. 聊天视图叠压**：目前顶栏 fixed 只作用于 Guide/Topic。让聊天消息也从顶栏下穿过需要动 `.chat-shell` 与侧栏高度，请给方案与风险评估。
- **D. 性能复测**：量化滚动帧率与合成层数量，确认收敛后是否真的降下来了。
- **E. 响应式**：分段 gradient 硬编码 `252px`（依赖侧栏 `flex: 0 0 252px`），窄屏与抽屉态怎么处理。

## 输出格式（严格遵守）

1. **一句话总评**（结论先说：当前还原度几成 / 是否该改）。
2. **问题清单**，按 **P0（明显不像 Apple 或影响可用）/ P1（还原度差距）/ P2（锦上添花）** 分级。每条必须给**可直接粘贴的完整 CSS**（选择器 + 全部属性值），不许只说"建议加强"。
3. **每条标注证据来源**：实测值 / 代码行号 / 官方原文引用；无证据的标 **【推断】**。
4. **末尾给 A/B/C 选项**让我选下一步，不要自作主张一次改完。
5. 改动后请自己跑一遍上面的脚手架验证，并在回复里贴出实测输出。
