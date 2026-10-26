# Liquid Glass v2 审查报告

> 审查对象：`web/static/guide.css` 第 2827 行起的 "Apple Liquid Glass theme v2 (2026-10-15)" 覆盖层
> 证据基础：**已实际读取 `guide.css`（3004 行）与 `templates/guide.html`、`static/guide.js`**，
> 因此下列结论中凡是引用了行号/色值的均为**已核实**；依赖渲染效果的仍标【推断】。
> 未使用截图（本次未提供）。
> 配套补丁：`docs/liquid-glass-v3.patch.css`（整段替换即可）

---

## 1. 总评

**还原度约 5.5 / 10 —— 它做出了 2020 年那代「磨砂亚克力面板」，但还没进入 Liquid Glass 的语境。**

最致命的一条不是参数，而是**结构**：`.topbar`、`.chat-sidebar`、`.composer` 都是静态 flex 项（`flex: 0 0 auto` / `flex: 0 0 252px` / `margin: 0 auto`），背后只有一层固定的平渐变，**没有任何内容从它们下面经过**。此时 `backdrop-filter` 的输出与一块纯 `rgba()` 填充在视觉上完全等价——玻璃之所以被读作玻璃，靠的是"下面有东西在动"。Apple HIG 里材质是 **chrome 压在 content 之上** 的产物，你现在的 DOM 里 chrome 和 content 是并排的，不是叠压的。

做对的部分（保留）：`blur → saturate` 顺序正确；`-webkit-` 前缀齐全；有 `@supports` 意识；hover 用自定义缓动而非 `ease`；`--guide-teal: #0f766e` 实测 4.86:1，本身就达标。

---

## 1.1 ⚠️ 实施后修正：报告里有两条结论被实测推翻

v3 已落地并用 Chrome 实测，`guide.css?v=20261015d`。过程中发现**报告本身的这两条建议是错的**，已就地纠正（保留原文以便对照）：

**修正 1 —— P0-1 不该用 `position: sticky`。**
实测 `body.chat-page` 是 `height:100vh + overflow:hidden` 的 app shell，
`document.scrollHeight === clientHeight === 900`，**文档根本不滚动**，sticky 毫无作用
（实测 computed 仍是 `relative`，我第一版就是这么写的，静默失效）。
真正滚动的是 `#view-guide` / `#view-topic`（`overflow-y:auto`，scrollHeight 4449 / client 900），
而 `#view-chat` 不滚动。正确做法是只对长滚动视图把顶栏改成 `fixed` 叠压，用 `:has()`
按 `hidden` 属性精确命中：

```css
body.chat-page:has(#view-guide:not([hidden])) .topbar,
body.chat-page:has(#view-topic:not([hidden])) .topbar {
    position: fixed; top: 12px; left: 14px; right: 14px; z-index: 30;
}
body.chat-page:has(#view-guide:not([hidden])) #view-guide,
body.chat-page:has(#view-topic:not([hidden])) #view-topic {
    padding-top: 78px; height: 100%;
}
```
实测各滚动位置穿过顶栏的元素数：**scrollTop 300→2 / 700→3 / 1200→12 / 2000→3 / 3000→10**，
玻璃终于有东西从下面经过。聊天视图保持原样（`topbarPos: relative`），无回归。

**修正 2 —— P0-5 不该用 `:where()`。**
基础样式第 1818 行 `.oai-section:not(.oai-section-gray) .oai-card` 本身就是 **(0,3,0)**；
`:where()` 把我的规则降到 (0,1,0)，连基础规则都打不过（实测卡片背景仍是 `#fcfcfc`）。
正确做法是**保持等特异性 (0,3,0) 靠源码顺序取胜**：

```css
.oai-section:not(.oai-section-gray) .oai-card { background-color: rgba(255,255,255,0.78); }
.oai-section .oai-card:hover                  { background-color: rgba(255,255,255,0.86); }
```
实测 hover：`rgba(255,255,255,0.78)` → `rgba(255,255,255,0.86)` ✅

---

## 2. 维度一：材质真实感 —— CSS 做不到什么（必须说明的取舍）

| Liquid Glass 特征 | CSS | 说明 |
|---|---|---|
| 背景模糊 + 提饱和 | ✅ | `blur() saturate()` |
| 亮度提升（浅色玻璃"发光"） | ✅ | `brightness(1.06)`，**原稿漏了** |
| 渐变折射边（上亮下暗） | ✅ | 伪元素 + `mask-composite: exclude` |
| 左上静态镜面高光 | ✅ | `radial-gradient` 叠加 |
| **真位移折射 lensing** | ❌ | 需采样背景像素再位移。`backdrop-filter: url(#svg)` 规范允许，但 **Chrome / Safari 均未实现 SVG 滤镜引用** |
| **随背景亮度自适应深浅** | ❌ | 无 `backdrop-luminance()`，只能靠 `prefers-color-scheme` 两套手工值 |
| **随滚动/视角的材质形变** | ❌ | 需 JS 逐帧驱动，与 `prefers-reduced-motion` 冲突 |
| 边缘色散 chromatic aberration | ❌ | 需像素级操作 |

**取舍结论**：不做真折射是正确的工程决策。差距只在"与真机并排对比"时可见；把 **渐变边 + 高光 + 层级纪律** 三件事做对即可。

---

## 3. 维度二 ~ 六：问题清单

### P0 — 明显不像 Apple / 影响可用性

#### P0-1 · 三块玻璃背后没有内容（头号问题，已核实）

```css
/* guide.css:1041 附近 */ .topbar       { flex: 0 0 auto; }         /* 无 position */
/* guide.css:~2280  */    .chat-sidebar { flex: 0 0 252px; overflow-y:auto; }
/* guide.css:~1340  */    .composer     { max-width:768px; margin:0 auto; }
```
三者都是 flex 兄弟节点，文档整体滚动，内容不会从它们下方穿过 → 它们的 `backdrop-filter` 采样到的是**一张静止的平渐变**，模糊结果恒等于一块纯色填充。

```css
.topbar   { position: sticky; top: 12px;  z-index: 30; }
.composer { position: sticky; bottom: 14px; z-index: 20; }
```
若父容器不是滚动容器导致 `sticky` 无效，退而求其次：让消息流用负 `margin-top` + 等量 `padding-top` 从顶栏下穿过。**这一条不修，其余所有参数调优的收益都要打折。**

#### P0-2 · 全文件 0 条 `prefers-*` 查询（已核实：`grep -n "prefers-" guide.css` 无命中）

而基础样式第 2750 行附近有 `.kb-panel { animation: kb-slide-in 0.18s ease-out; }`——抽屉每次打开都有位移动画，却没有降低动效开关。

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
    scroll-behavior: auto !important;
  }
  .oai-card:hover { transform: none; }
  .kb-panel { animation: none; }
}
```

#### P0-3 · 15 处硬编码浅灰文字不过 WCAG AA（已核实 + 已实算）

按你的配色反算玻璃实际底色：blob `rgba(186,222,255,.5)` over `#f1f4f8` → `#D5E9FB`，L=**0.795**；卡片 `rgba(255,255,255,.44)` over 之 → L=**0.881**。

| 色值 | 出现 | 对比度 | 判定 |
|---|---|---|---|
| `--guide-muted: #5f6b6a` | 变量，几十处 | **4.90:1** | ✅ 达标 |
| `#8a8a99` | 8 处（1872/1944/1967/2033/2197/2281/2292/2334/2342） | **3.01:1** | ❌ |
| `#8a9494` | 1573/1634 | **2.76:1** | ❌ |
| `#8a9695` | 1460 | ~2.8:1 | ❌ |
| `#9aa7a6` / `#9aa5a4` | 1370/1578 | **2.20:1** | ❌❌ |
| `#9fb3b1` | 2651 | ~2.4:1 | ❌ |

```css
:root { --tx-3: #4a5453; }   /* 6.6:1 */
.oai-card p, .oai-card li, .oai-card-meta, .sources-head,
.sidebar-meta, .kb-meta, .oai-note, .chat-meta,
.kb-file small, .oai-hero-banner p { color: var(--tx-3); }
```
> 好消息：`--guide-teal: #0f766e` 实测 **4.86:1**，作为文字/链接已经合规，不需要动。作为填充底配白字是 5.47:1，也合规。

#### P0-4 · 嵌套 `backdrop-filter`：视觉无效 + 白付性能

Filter Effects L2：带 `backdrop-filter` 的元素成为 **Backdrop Root**，其**后代**的 `backdrop-filter` 只能采样"根内"内容（= 父元素自己的背景，透明）。所以：

- `.sidebar-newchat` / `.sidebar-action`（在玻璃 sidebar 内）、`.topbar-lang`（在玻璃 topbar 内）、`.kb-close` / `.kb-drop`（在玻璃 panel 内）—— **纯 no-op，却各付一次合成层 + 模糊 pass**。
- 反过来说："玻璃叠玻璃不会更糊"，只是叠了层半透明白 → 观感变成**奶白塑料**。Apple HIG 明令禁止 overlapping translucent materials。

**更极端的一处（已核实）**：`.chat-msg.user` 基础样式是 `background: #f1f3f4` **不透明**，v2 却给它加了 `backdrop-filter`——模糊结果被自己的不透明背景 100% 遮住，**彻头彻尾的浪费**。

```css
.sidebar-newchat, .sidebar-action, .topbar-lang, .kb-close, .kb-drop,
.chat-msg.bot, .chat-msg.user {
  -webkit-backdrop-filter: none; backdrop-filter: none;
}
```
另外 `.chat-msg.bot` 基础样式无背景、`align-self: stretch` → 每条 bot 消息是一条全宽模糊带，是页面里数量最不受控的模糊层。

#### P0-5 · 特异性 bug：卡片 hover 变白根本没生效（已核实）

```css
/* 2919 */ .oai-section:not(.oai-section-gray) .oai-card { background: rgba(255,255,255,0.44); }
```
特异性 **(0,3,0)** > `.oai-card:hover` **(0,2,0)** → hover 的 `.58` 永远被覆盖。

```css
:where(.oai-section:not(.oai-section-gray)) .oai-card { background-color: rgba(255,255,255,0.78); }
.oai-card:hover { background-color: rgba(255,255,255,0.86); }
```

#### P0-6 · `@supports not` 回退只兜了 5 个选择器

漏掉 `.kb-drop`、`.kb-file`、`.kb-stats div`、全部胶囊按钮、`.chat-msg`、`.oai-hero-banner`、`.story-hero`、`.oai-link`——这些会停在 0.35~0.50 透明度且**无模糊**，对比度直接崩。且回退只改了 `background`，没改边框（很淡的白边在纯白底上等于消失）。完整版见补丁第 8 节。

---

### P1 — 还原度差距

#### P1-1 · 双描边 = 1.5px 白塑料圈
`border: 1px solid rgba(255,255,255,.45)` **加上** `inset 0 0 0 0.5px rgba(255,255,255,.30)` ≈ 1.5px 均匀白边。真实玻璃边缘是**顶亮、两侧衰减、底转暗**的 hairline 渐变。

```css
.oai-card::before {
  content: ""; position: absolute; inset: 0; border-radius: inherit;
  padding: var(--hairline);
  background: linear-gradient(180deg,
      rgba(255,255,255,0.95) 0%, rgba(255,255,255,0.50) 38%,
      rgba(255,255,255,0.10) 70%, rgba(120,150,180,0.22) 100%);
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
          mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor; mask-composite: exclude;
  pointer-events: none;
}
```

#### P1-2 · 材质档位没拉开，且 blur 与 fill 反向搭配
现有 topbar 28/0.50、sidebar 30/**0.34**、composer 24/0.50、card 28/0.44、panel 40/0.62。
- **24 / 28 / 30 感知上无差别**（人眼对 blur 半径的分辨阈值约 1.5×），等于没有层级；
- **sidebar 是"最糊 + 最透"**，方向反了。Apple 的规律是**越厚 = 越糊 = 越不透**；0.34α + 30px 的结果是"雾蒙蒙的 haze"，不是玻璃。

```css
.topbar       { --g-blur:30px; --g-fill:rgba(255,255,255,.58); --g-sat:165%; }
.chat-sidebar { --g-blur:30px; --g-fill:rgba(255,255,255,.52); --g-sat:160%; }
.composer     { --g-blur:36px; --g-fill:rgba(255,255,255,.60); --g-sat:170%; }
.kb-panel     { --g-blur:48px; --g-fill:rgba(255,255,255,.72); --g-sat:175%; }
.oai-card     { --g-blur:16px; --g-fill:rgba(255,255,255,.78); --g-sat:150%; }
/* 统一基元 */
backdrop-filter: blur(var(--g-blur)) saturate(var(--g-sat)) brightness(1.06);
```
> 卡片：Tahoe / iOS 26 里内容面（卡片、列表、气泡）基本不透明，玻璃只给 chrome。0.78 + 16px 是折中；要彻底对齐就 0.90 + 无模糊。

#### P1-3 · 缺 `brightness()` —— 浅色玻璃的关键是"比背景亮一点"，不是"白"
`backdrop-filter: blur(...) saturate(...) brightness(1.06)`

#### P1-4 · `saturate(190%)` 过冲（法则见 Q&A 4）
0.44α 配 190% 会把粉彩推成糖果色，材质变"有色塑料"。建议 **150%（薄）→ 175%（厚）**，越低 α 越不需要高饱和。

#### P1-5 · 缺通用 `:focus-visible`（已核实：全文件仅 4 条 focus 规则，且都是输入框/`:focus-within`/`kb-drop`）
```css
:where(a, button, input, textarea, select, [tabindex]):focus-visible {
  outline: 2px solid var(--guide-teal); outline-offset: 2px; border-radius: 8px;
}
```
用 `outline` 而非 `box-shadow`：outline 不会被 `overflow`/backdrop 裁剪。

#### P1-6 · 缺 `:active` 按下态（Apple 最有辨识度的一帧）
```css
.sidebar-newchat:active, .sidebar-action:active, .topbar-lang:active,
.oai-btn-ghost:active, .kb-close:active, .oai-card:active {
  transform: scale(0.985); transition-duration: 0.10s;
}
```

#### P1-7 · hover 是 Material 语言
`translateY(-3px)` + `0 20px 52px rgba(...,.14)` 是 Material elevation。Apple 是**轻抬 2px + 阴影微增 + 0.25~0.3s**。
另外：hover 改 `box-shadow` 会让带 `backdrop-filter` 的元素**每帧重算模糊**——这是全页最贵的操作。做法：阴影保持静态，用 `::after` 的 `opacity` 过渡代替。

#### P1-8 · 中文字体栈在 Windows 空窗
`PingFang SC` / `Hiragino Sans GB` 均 Apple 独占，Windows 掉到 `sans-serif` → Latin 走 Arial，与 SF 字面差距很大。
```css
font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI",
  "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans SC", sans-serif;
```

#### P1-9 · 中文负字距
CJK 全角等宽、自带边距，负字距会造成字面相撞。CSS 无法按字符集选择（`:lang()` 要改 HTML），只能按选择器分：
```css
body.guide-page :is(h1,h2,h3), body.chat-page :is(h1,h2,h3) { letter-spacing: -0.015em; }
.sidebar-newchat,.sidebar-action,.topbar-lang,.oai-btn-ghost,.kb-close,.oai-link { letter-spacing: 0; }
```
> ⚠️ 基础样式 `.oai-section h2` 已是 `-0.025em`（第 1780 行），v2 的 `-0.02em` 会覆盖它。**若这些 h2 含中文，必须归 0。**

#### P1-10 · `background-attachment: fixed` 在 iOS Safari
行为不一致（部分版本按 `scroll` 处理、滚动抖动）且重绘昂贵。改用 fixed 伪元素层：
```css
body.chat-page::before, body.guide-page::before {
  content:""; position: fixed; inset: 0; z-index: -1; pointer-events: none;
  background: /* 三条 radial + linear，照搬原值 */;
}
body.chat-page, body.guide-page { background: #eef2f7; }
```

#### P1-11 · 0.5px 描边跨浏览器差异
`box-shadow` 的 0.5px spread 在 Chrome 1x 屏常被抹成 0 或进位成 1px，Safari 抗锯齿近似，Firefox 又不同。用 `border` + 媒体查询切变量更稳：
```css
:root { --hairline: 1px; }
@media (-webkit-min-device-pixel-ratio:1.5), (min-resolution:144dpi) { :root { --hairline: .5px; } }
```

#### P1-12 · `.oai-section-gray` 的 `100vmax` 扩散 hack（**修正说明**）
⚠️ 我原以为会有巨型图层问题，**实测基础样式第 1774 行已有 `clip-path: inset(0 -100vmax)`**，`clip-path` 会裁剪包括 `box-shadow` 在内的全部绘制，所以**没有 30 万 px 图层问题**。降级为 P1，但仍有两个真实问题：

1. 整条横向色带把背景**压平成单一浅灰**，玻璃卡片下面没有任何东西可折射——与主题目标自相矛盾；
2. `clip-path` 会创建层叠上下文，**可能**成为 Backdrop Root 而让内部卡片的 `backdrop-filter` 采样错误【推断：需实测】。

```css
.oai-section-gray { background:none; box-shadow:none; clip-path:none; position:relative; }
.oai-section-gray::before {
  content:""; position:absolute; inset-block:0; inset-inline:-32px; z-index:-1;
  background: linear-gradient(180deg, rgba(243,247,251,.62), rgba(233,240,247,.52));
}
```

#### P1-13 · 同屏 backdrop-filter 数量【推断：取决于列表长度】
sidebar 会话行 N、卡片 6~12、卡片上 ghost 按钮 N×卡片数、kb-file 10~30、`chat-msg` **无上限**。满载 60~120 个模糊层。原则：**只有浮在非玻璃内容之上的"栏/浮层"才配用玻璃**。

#### P1-14 · `.kb-panel` 残留 teal 投影（已核实，第 2750 行附近）
v2 没有覆盖 `.kb-panel` 的 `box-shadow: -12px 0 32px rgba(15,118,110,.12)`，与"中性阴影"的方向不一致。
```css
.kb-panel { box-shadow: -12px 0 32px rgba(24,36,52,0.14); }
```

---

### P2 — 锦上添花

| 项 | 代码 |
|---|---|
| 减弱透明度（Safari 17+ / macOS 辅助功能） | `@media (prefers-reduced-transparency: reduce){ .topbar,.chat-sidebar,.composer,.oai-card,.kb-panel{ --g-fill:rgba(255,255,255,.96); backdrop-filter:none; } }` |
| 高对比度 | `@media (prefers-contrast: more){ :root{--tx-2:#3a3a3c;--tx-3:#48484a;} .oai-card{--g-fill:rgba(255,255,255,.92);} }` |
| 触摸设备粘滞 hover | 所有 `:hover` 包进 `@media (hover: hover)` |
| 数字对齐 | `.kb-stats div { font-variant-numeric: tabular-nums; }` |
| 浅底文字更贴近 Apple | `body { -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }` |
| CJK/Latin 混排标点挤压（Chrome 123+/Safari 18+，**需实测**） | `:is(h1,h2,h3,p,li){ text-spacing-trim: space-first; }` |
| 为暗色预留 | `:root { color-scheme: light; }` |

> 已核实无需处理：`.oai-card-media` 已有 `border-radius: 11px; overflow: hidden;`（第 ~1800 行），148px 缩略图不会顶破 22px 圆角，嵌套圆角比例也合理。

---

## 4. 快问快答

**Q1：为什么不用 SVG filter / displacement-map 做真折射？代价是什么？**
`feDisplacementMap` 只能采样**元素自身**渲染结果，拿不到"我背后画了什么"；`backdrop-filter: url(#f)` 规范允许但 Chrome 与 Safari 至今未实现 SVG 滤镜引用，只支持滤镜函数。真折射只能 canvas/WebGL 重绘背景 → 跑位移着色器 → 贴在元素后，等于你自己实现半个合成器：每帧重采样、滚动抖动、与 `prefers-reduced-motion` / `prefers-reduced-transparency` 冲突、还要写套降级。Apple 能做是因为它有原生合成器对整棵 layer tree 的 GPU 访问权。收益只在并排对比时可见，不值得。

**Q2：为什么背景 blob 去掉了动画？Apple 官网是静是动？**
Apple 官网背景渐变/主视觉**默认静态**——只在滚动视差或一次性入场时动，且严格服从 reduced-motion；macOS/iOS 壁纸也默认静态（动态壁纸需用户主动开）。所以静态是对的。更关键的是性能：**动画化玻璃背后的内容 = 每一帧让 N 个模糊层全部重算**，这是你能对这个页面做的最贵的一件事。想加"活气"就动元素自己的 `transform` / 高光 `opacity`（纯合成器属性），别动背景。

**Q3：加暗色模式，这套变量怎么重构？**
把字面量抽成 `--g-blur / --g-fill / --g-sat / --rim / --tx-*` 就是为了这个。加暗色**只覆盖令牌，不重复任何选择器**：
```css
@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --g-fill: rgba(28,28,30,0.72);
    --g-sat: 140%;                      /* 暗色下要降饱和，否则彩色 blob 会发光溢出 */
    --rim: linear-gradient(180deg,
        rgba(255,255,255,0.16) 0%, rgba(255,255,255,0.04) 45%, rgba(0,0,0,0.30) 100%);
    --tx-1: #f5f5f7; --tx-2: #a1a1a6; --tx-3: #8e8e93;
  }
  .topbar,.chat-sidebar,.composer,.oai-card,.kb-panel {
    box-shadow: 0 1px 2px rgba(0,0,0,0.40);   /* 暗色下投影几乎无效，靠边刻画轮廓 */
  }
}
```
三个要点：暗色下 `brightness()` 要改成 <1（约 0.92）、`saturate()` 要降、投影要让位给描边。

**Q4：`saturate(190%)` 这类数值怎么定的？经验法则？**
玻璃会**去饱和**——先做区域平均（blur），再盖一层白（fill），两步都往灰里拉，所以要用 `saturate()` 补回来，补偿量与"盖了多少白"成正比：

> **`saturate ≈ 100% + α_fill × 120%`，上限 180%**
> α=0.26 → 131% ｜ α=0.44 → **153%** ｜ α=0.58 → 170% ｜ α=0.72 → 186%（封顶 180%）

0.44α 配 190% 过冲约 25%，会读到"有色塑料"。另两条：① 滤镜顺序必须 `blur → saturate → brightness`（先模糊再调色，反了会把颜色边缘糊掉）；② `saturate` 会把已饱和的品牌色推出 sRGB 色域，teal 尤其容易溢出，所以 teal 出现处再降一档。

---

## 5. 落地结果（v3，2026-10-15 17:2x 已应用并实测）

改动文件 | 说明
--- | ---
`web/static/guide.css` | 第 2827 行起的 v2 覆盖层整段替换为 v3（备份 `guide.css.bak-20261015-172314`）
`web/templates/guide.html` | 版本号 `?v=20261015b` → `?v=20261015d`
`docs/liquid-glass-v3.patch.css` | 与已应用内容同步（直接从 guide.css 回抽，不再是草稿）
`docs/liquid-glass-v3-shots/` | 5 张实测截图

Chrome 实测（1440×900，**非推断**）：

| 检查项 | 结果 |
|---|---|
| 顶栏在长滚动视图 | `position: fixed`，与 `#view-guide` 重叠，内容穿行 ✅ |
| 聊天视图回归 | `topbar: relative`、composer (462,811,768,52)、sidebar (0,66,252,834)、文档无溢出 ✅ |
| 卡片 hover | `0.78 → 0.86` ✅ |
| 抽屉 `.kb-panel` | `blur(48px) saturate(1.75) brightness(1.06)` / `rgba(255,255,255,.72)` ✅ |
| 嵌套 blur 已撤 | `.sidebar-action` 等 computed `backdrop-filter: none` ✅ |
| 次要文字 | `.oai-source-note/.sidebar-label/.composer-note` = `rgb(74,84,83)`（6.6:1）✅ |
| 灰 section 全出血 | `::before` 宽 1440px = 视口宽（自身 1120px，两侧各 -160px）✅ |
| 媒体查询 | reduced-motion 1 / reduced-transparency 1 / @supports 兜底 1 ✅ |
| 焦点环 | `a.oai-btn-ghost` → `outline: 2px solid #0f766e`，offset 2px ✅ |
| JS 错误 | 0 ✅ |

## 5.1 v3.1 —— 顶栏 / 侧栏 L 形连续玻璃（2026-10-15 晚，用户指出"很割裂"）

用户截图指认聊天视图的顶栏与侧栏割裂。实测定位到**三个量化来源**，全部已修（`?v=20261015f`）：

| # | 割裂来源（实测证据） | 修法 |
|---|---|---|
| 1 | **顶栏 x=14 起 + 圆角 22px，侧栏 x=0 直角**。左边缘那条 14px 竖缝里露出的是 `BODY` 背景（`elementFromPoint(7, 顶栏内)` 返回 `BODY`）——上下两段材质断开，这是主因 | 顶栏 `margin-left:0` + `border-radius: 0 22px 22px 0`，左端通到屏幕边；fixed 视图同步 `left:0` |
| 2 | **fill 不一致**：顶栏 0.58 vs 侧栏 0.52，L 形相接处（y=66，x 0~252）有亮度差 | 顶栏背景改成**精确像素分段 gradient**：0~252px 用 0.52（与侧栏同色），252px 之后 0.58。blur 两段相同（整块 backdrop-filter），拼接处无痕 |
| 3 | **玻璃上叠常驻描边胶囊**：侧栏的 New chat / Training materials（`.42`+白边）、顶栏的 中文 / ＋New chat（后者竟是**不透明白** `rgb(255,255,255)`+灰边） | 全部无边框化：`background/border/box-shadow` 透明，hover 才出现 0.55 白色高亮块，active 0.72 —— Apple toolbar 的标准做法 |

另：侧栏顶边那条 1px 与顶栏底边重叠，已去掉侧栏的（`border-top-width:0`），让顶栏底边成为 L 形内部唯一分隔线。

**保留不动的**：`.topbar-tab.active` 的白块——那是 segmented control 的选中态，本来就该是实心。

实测（`?v=20261015f`）：左缝 `elementFromPoint` → `NAV` ✅；分段 gradient 含 `252px` ✅；
五个按钮 computed 全部 `rgba(0,0,0,0)` ✅；`.topbar-newchat` hover → `0.55` ✅；
布局无回归（topbar [0,12,1426,54]、sidebar [0,66,252,834]、composer [462,811,768,52]、overflow 0）✅；JS 错误 0 ✅。
截图 `docs/liquid-glass-v3-shots/6-chat-lshape.png` / `7-guide-lshape.png` / `8-chat-final.png`。

> 已知边界：9.2 的分段 gradient 硬编码 `252px`，依赖侧栏 `flex: 0 0 252px` 的固定宽度；
> 若将来侧栏改成响应式宽度，这里要跟着改。

## 5.2 v3.2 —— 对齐 Apple HIG《Materials》官方原文（版本 `?v=20261015h`）

前面几轮的依据是规范与经验，这一轮改成**以官方原文为准**。来源：
- <https://developer.apple.com/design/human-interface-guidelines/materials>
- WWDC25《Meet Liquid Glass》(219) — Principles 章节
- WWDC25《Get to know the new design system》(356) — Design Language 章节

### 官方原文 vs 本项目的对照

| 官方原文（verbatim） | 本项目原状 | 处置 |
|---|---|---|
| **"Don't use Liquid Glass in the content layer."** | `.oai-card` / `.oai-hero-banner` / `.story-hero` 都是 `backdrop-filter` 玻璃 —— **违规** | 内容层退出 Liquid Glass，改 standard material（`none` + 不透明 0.88 + hairline），折射边/高光伪元素 `display:none` |
| **"Liquid Glass forms a distinct functional layer for controls and navigation elements — like tab bars and sidebars — that floats above the content layer."** | 玻璃散落在卡片、气泡、按钮上 | 玻璃收敛到 4 个导航/控件面：`.topbar` `.chat-sidebar` `.composer` `.kb-panel` |
| **"Avoid putting glass in the content layer and avoid putting within or on top of other glass elements."** | 侧栏/顶栏按钮叠玻璃 | v3.1 已无边框化；v3.2 后内容层无玻璃 |
| **"concentric shapes calculate their radius by subtracting padding from the parent's."** / "One place this often shows up is nested containers — like artwork in a card." | 卡 22 / 缩略图 11，非同心（官方说的 "pinched or flared"） | 卡 **28** / 缩略图 **14**（实测 `.oai-card.has-media` padding 是 `14px 14px 18px`，故 28−14=14） |
| **"The variants should never be mixed."**（Regular vs Clear） | 未使用 Clear | ✅ 全站只用 Regular，符合 |
| **"Only use clear Liquid Glass for components that appear over visually rich backgrounds."** | 未使用 | ✅ |
| **"Help ensure legibility by using vibrant colors on top of materials."** + "Thicker materials… provide better contrast" | 卡片 0.78 上次要文字 6.6:1 | 内容层改 0.88 后，次要文字实测 **7.6:1** ✅ |
| **"Use Liquid Glass effects sparingly."** | 同屏 60~120 个模糊层 | 收敛后只剩 4 个玻璃面 + 抽屉，模糊层数降一个数量级 |

### 官方有、但 Web 上做不了的部分（明确取舍，非遗漏）

1. **Lensing（真折射）**——"dynamically bends and concentrates light"。需采样背景像素再位移；`backdrop-filter: url(#svg)` 规范允许但 Chrome/Safari 未实现。
2. **Adaptivity**——"adapts based on the content beneath it… Small elements, symbols, and glyphs flip from light to dark"。CSS 无法读取下方内容的亮度。
3. **Scroll Edge Effects**——"blurring and reducing the opacity of background content" 让内容溶进栏里。CSS 无滚动位置查询，静态 mask 会在静止时误伤首屏内容顶部（把 hero 顶边磨淡），故**未启用**。若要试：
   ```css
   body.chat-page:has(#view-guide:not([hidden])) #view-guide {
     -webkit-mask-image: linear-gradient(180deg, transparent 0 78px, #000 94px, #000 100%);
             mask-image: linear-gradient(180deg, transparent 0 78px, #000 94px, #000 100%);
   }
   ```
   代价：mask 会建层叠上下文，且静止时首屏顶部 16px 会被磨淡。
4. **材质随交互"内部发光"**——"materials illuminate from within… reflect on other Liquid Glass elements"。可用 `::after` opacity 动画近似，但与 `prefers-reduced-motion` 冲突，未做。

### 实测（`?v=20261015h`）

```
LAYERS  topbar blur(30px) saturate(1.65) brightness(1.06)
        sidebar blur(30px) saturate(1.6)  brightness(1.06)
        composer blur(36px) saturate(1.7)  brightness(1.06)
        kbpanel blur(48px) saturate(1.75) brightness(1.06)
        card / hero / story  →  none          ✅ 内容层零玻璃
CARD    radius 28px · bg rgba(255,255,255,0.88) · padding 14px 14px 18px
        media radius 14px · ::before display:none
GLASS_ON_CONTENT  0        JS 错误 0
```

> ⚠️ 过程中又修了两处自测出来的错：① `body.chat-page .oai-card` 是 (0,2,1)，
> 打不过基础样式的 `.oai-section:not(.oai-section-gray) .oai-card` (0,3,0)，
> 卡片背景一度仍是 0.78 —— 补了等特异性且更靠后的规则；
> ② 同心圆角基数一开始用了 22（无缩略图卡的 padding），实测带缩略图的卡走
> `.oai-card.has-media` padding=14，正确值是 28−14=14。

## 6. 落地顺序建议

1. **P0-1**（让内容从栏下经过）→ 不修这条，后面全是白调；
2. **P0-2 / P0-3 / P0-6**（reduced-motion、浅灰文字、降级兜底）→ 合规硬伤；
3. **P0-4**（撤掉嵌套 blur）→ 一次性砍掉一半合成层，且几乎无视觉损失；
4. **P1-1 / P1-2 / P1-3**（渐变描边、档位拉开、加 brightness）→ 观感提升最大的三步；
5. 其余按 P1 → P2 顺序。
