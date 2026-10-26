# Apple Liquid Glass v4 —— 三端视觉统一（2026-10-16）

> 结论先说：**「四不像」的根因是三套互不兼容的设计语言并存**，不是某一处样式写坏了。
> 本轮把三端统一到 Apple HIG 一套语言上，并已用无头浏览器实测验收。

---

## 1. 问题诊断：三套设计语言

排查（`grep` 全仓 + 浏览器实测）出项目里同时存在三个强调色 / 三套中性色 / 两种字体：

| 界面 | 路径 | 原强调色 | 原字体 | 原材质 |
|---|---|---|---|---|
| 网页端 | `web/` → `/guide` | teal `#0f766e`（32 处引用 + 24 处硬编码） | Google Fonts **Inter** | 玻璃 v3.2（较成熟） |
| 桌面端 | `desktop/` | ChatGPT 绿 `#10a37f` **+** antd 主色藏青 `#2e6da4`（同一页两套色） | Inter | **零玻璃**，暗色是 ChatGPT 的 `#202123/#343541` |
| 遗留状态页 | `web/` → `/legacy` | ChatGPT 绿 `#10a37f` | Inter | 纯白卡片 |

三个可直接量化的硬伤：

1. **桌面端 ChatGPT 绿 `#10a37f` 在白底上只有 3.20:1**，低于 WCAG AA 的 4.5:1 —— 不达标。
2. **桌面端 `ConfigProvider` 用 `#2e6da4`、`styles.css` 用 `#10a37f`**，同一页面两套强调色互相打架。
3. **`/guide` 的主 CTA 是纯黑 `#0d0d0d` 胶囊**，而其余控件全用 teal —— 强调色没有落到主操作上，页面读起来像 OpenAI 而不是 Apple。

---

## 2. 统一方案：一套 Apple 系统色

### 2.1 强调色（浅色 / 深色）

| 用途 | 浅色 | 深色 | 对比度 |
|---|---|---|---|
| 文字 / 描边 / 图标 | `#0066cc` | `#409cff` | 白底 **5.57:1** ✅AA（同 apple.com 链接蓝） |
| 实心按钮底（白字） | `#0071e3` | `#0a84ff` | 白字 **4.70:1** ✅AA（同 apple.com 按钮蓝） |
| 按下 / 悬停 | `#006edc` | `#409cff` | — |

> 对比度全部用 WCAG 相对亮度公式实算，不是估的。候选值对照：
> `#007aff`（Apple 浅色 systemBlue）只有 4.02:1，`#0a84ff` 只有 3.65:1，
> 都过不了 AA，所以文字档位最终选了 apple.com 实际在用的 `#0066cc`。

### 2.2 中性色（对齐 HIG），**字体改系统 SF Pro**

| 角色 | 值 | 对比度 |
|---|---|---|
| label（正文/标题） | `#1d1d1f` | 16.8:1 |
| secondaryLabel | `#6e6e73` | 5.07:1 ✅AA |
| separator | `#e5e5ea` | — |
| surface | `#ffffff` | — |
| groupedBackground | `#f2f2f7` | — |

**去掉 Google Fonts 的 Inter 外链**（`guide.html` / `legacy.html` 各删 3 行 `<link>`），
字体栈改为 `-apple-system, BlinkMacSystemFont, "SF Pro Text", …` —— macOS 上直接解析为真 SF Pro，
顺带省掉一次跨域字体请求。Windows/Linux 回退 `Segoe UI` / `PingFang SC` / `Microsoft YaHei`。

---

## 3. 各文件改动清单

### 3.1 `web/static/guide.css`（3377 → 3688 行）

| 位置 | 改动 |
|---|---|
| `:root`（原 3–13 行） | 9 个令牌换 Apple 值；新增 `--guide-accent-fill/-strong/-btn-disabled`、`--guide-warn/-danger/-recording`；**旧名 `--guide-teal*` 保留为别名**，任何外部引用都不会断 |
| 基础层 | 60 余处硬编码 teal / 绿调中性色统一替换（`#0f766e` 18 处、`#134e4a` 6 处、`#f0fdfa` 9 处…）；4 处 teal 阴影 rgba 同步 |
| 字体 | 3 处 `Inter` 栈 → 系统 SF Pro 栈 |
| **§11 新增** | 见下 |

**§11 新增内容（本轮的核心）：**

- **11.1** 半径刻度令牌（`--r-xs/sm/md/lg/xl/pill`）+ `--focus-ring`
- **11.2** `::selection` / `accent-color` / Apple 覆盖滚动条（11px、深灰胶囊、默认隐形）
- **11.3** 环境光**补 2 个光斑**。原来只有 3 个柔光斑，滚到页面中下部就是一片纯色渐变，
  玻璃在那里退化成「磨砂塑料」——这是最容易被看出破绽的地方
- **11.4** **分段控件按 Apple 分段控件重做**：轨道 `rgba(118,118,128,.12)` + 内阴影（凹陷感），
  滑块投影改「大而软 + 小而定」两层。原来只是一块浅灰上放一块白
- **11.5** 顶栏 52pt + 品牌字重
- **11.6** 内容层卡片改 **Apple standard material**：纯白 systemBackground + 0.5px 分隔线 + 双层静投影；
  hover 只微增投影 + 2px 抬升（Apple 的 hover 是克制的，不是 Material 的大幅浮起）
- **11.7** 抽屉内控件同心圆角
- **11.8** 侧栏行改 macOS app 的**中性**选中态（蓝留给分段控件与主按钮）
- **11.9** 焦点环统一到 accent
- **11.10** **主 CTA `.oai-btn-dark` 纯黑 → apple.com 蓝胶囊**；
  修掉 `.oai-btn-ghost` / `.oai-link` 的**隐形按钮 bug**——
  主题层 §4 给它们设的是「白底 .42 + 白边 .60」（那是为压在玻璃上写的），
  但它们实际落在**纯白卡片**上，等于一个看不见的按钮

### 3.2 `web/templates/guide.html` / `legacy.html`

- 删 Google Fonts Inter 的 3 行 `<link>`
- 版本号 `guide.css?v=20261015h` → `?v=20261016b`；`legacy.css` / `legacy.js` 加 `?v=20261016a`

### 3.3 `web/static/legacy.css`（整文件重写，~300 行）

统一调色板与字体；按「设置面板」性质给卡片 14px 圆角（不是 apple.com 那种全胶囊）；
状态点用 Apple 系统红绿；**不加玻璃**（内容层）；补 `prefers-reduced-motion` 与
`prefers-reduced-transparency`。

### 3.4 `desktop/src/App.tsx`

`ConfigProvider` token 从 `colorPrimary: "#2e6da4"`（藏青）换成 Apple 系统蓝，
并补齐 label / separator / surface / 圆角刻度 / `boxShadowSecondary` 等一整套，
浅色深色各一套（`lightTokens` / `darkTokens`）。

### 3.5 `desktop/src/styles.css`（1158 → 1463 行）

- 浅色段 33 种硬编码色 → Apple 值；深色段把 **ChatGPT 暗色 `#202123/#343541/#40414f` 换成 Apple 暗色 `#1c1c1e/#2c2c2e/#38383a`**
- 字体去 Inter
- 末尾新增 Apple Liquid Glass 分节：
  - `body` 挂环境光（`background-attachment: fixed`，与网页端同一条光）
  - antd `Layout` 全透明让位
  - **玻璃功能层**：`.chat-sidebar` / `.chat-header` / `.chat-footer` 同一填充值 → 左上角拼成连续 L 形
  - **浮层玻璃**：`.ant-modal-container` / `.ant-drawer-content` / `.ant-popover-inner` / `.ant-dropdown-menu` / `.ant-select-dropdown` / `.ant-message-notice-content` / `.ant-tooltip-inner`
  - 遮罩 `rgba(0,0,0,.28)` + `blur(3px)`
  - **内容层**：`.chat-content` 透明铺底，各种卡片 `var(--surface)` 不透明 + hairline + `backdrop-filter: none`
  - 输入框改 Apple「字段填充」`rgba(120,120,128,.12)` 而不是再套一层玻璃（`.chat-footer` 已是 Backdrop Root，嵌套模糊是 no-op）
  - `prefers-reduced-motion` / `-transparency` / `@supports not backdrop-filter` 三重降级

> ⚠️ antd **v6** 的 Modal 内层类名是 `.ant-modal-container`（不是 v5 的 `.ant-modal-content`），
> 已用 `node_modules/antd/dist/antd.css` 实测确认；`ant-modal-content` 在 v6 里 0 处匹配。

---

## 4. 实测验收（无头 Chrome + playwright，1440×900 @2x）

### 4.1 硬约束：玻璃只在功能层

遍历所有元素的 `getComputedStyle(el).backdropFilter !== "none"`：

| 界面 | 玻璃元素 | 落位 |
|---|---|---|
| 网页端 `/guide`（Chat 视图 / Guide 视图 / 抽屉打开态） | **5** | `.topbar`(30px) `.chat-sidebar`(30px) `.composer`(36px) `.kb-drawer-backdrop`(2px) `.kb-panel`(48px) —— **全部 functional** |
| 网页端**内容层违规** | **0** | ✅ |
| 桌面端（浅色） | 3 | `.chat-sidebar` / `.chat-header` / `.chat-footer`（30px / 1.7 / 1.04） —— 全 functional |
| 桌面端（深色） | 3 | 同上 |
| 桌面端**内容层违规** | **0** | ✅ |
| `/legacy` | 0 | ✅ 内容页本来就不该有玻璃 |

### 4.2 关键计算值（浏览器实读，非推断）

```
--guide-accent        #0066cc        --guide-accent-fill  #0071e3
--guide-ink           #1d1d1f        --guide-muted        #6e6e73
--guide-line          #e5e5ea        --hairline           0.5px（Retina 命中）
body 字体             -apple-system

.oai-card            bg rgb(255,255,255) · backdropFilter none · radius 28px
                     border 0.5px rgba(60,60,67,.1)
                     shadow 0 1px 2px rgba(0,0,0,.04), 0 6px 20px rgba(0,0,0,.05)
.oai-card-media      radius 14px  ← 28 − 14 = 14，同心成立
.oai-card:hover      transform translateY(-2px)，背景保持白色（不变玻璃）
.topbar-tabs         bg rgba(118,118,128,.12) + 内侧 0.5px 线与 1px 内阴影
.topbar-tab.active   bg #fff · color rgb(29,29,31) · 双层投影
.oai-btn-dark        bg rgb(0,113,227) · color #fff · radius 999px
.oai-btn-ghost       bg #fff · border 1px rgba(60,60,67,.18)

桌面端 浅色  --accent #0071e3 · --g-fill rgba(255,255,255,.62) · --label #1d1d1f
桌面端 深色  --accent #0a84ff · --g-fill rgba(44,44,46,.66)   · --label #f5f5f7
桌面端 .chat-header 高度 52px（Apple 工具栏）
桌面端 .composer    bg rgba(120,120,128,.12) · radius 20px
```

### 4.3 构建与类型检查

- `desktop`：`tsc -b` **exit 0**；`vite build` **exit 0**（3176 modules，CSS 22.85 kB → gzip 5.30 kB）
- 网页端 CSS：花括号 / 注释配平（530/530、152/152）；三处字体栈替换成功

---

## 5. 备查

- **备份**：`_backup-liquidglass-20261016-000810/`（改动前 6 个文件的原始副本）
- **截图**：`docs/liquid-glass-v4-shots/`（8 张：网页端 3 视图 / 分段控件 / 状态页 / 桌面端深浅色 + 设置页）
- **可粘贴主题层**：`docs/liquid-glass-v4.patch.css`（§0~§11 完整拷贝，881 行）
- **上一版基线**：`docs/liquid-glass-v3.patch.css`（v3.2，保留作为历史记录）
- 校验脚手架：`playwright-core`（`~/.workbuddy/binaries/node/workspace/node_modules`）+ 系统 Chrome
