# 侧栏改版 v5 — 变更记录

> 2026-10-16 第二轮。触发：用户截图反馈「侧边栏能不能改一下」。
> 上一轮（v4）只换了侧栏的**颜色与字体**，**控件形态**没动 —— 本轮专门补上。

改动文件（3 个）：
`web/static/guide.css`（§11.11，+213 行）、`web/templates/guide.html`、`web/static/guide.js`（1 行 i18n）
备份：`_backup-liquidglass-20261016-sidebar/`

---

## 1. 三个可测量的缺陷（截图复现 → 定位到代码）

### 缺陷 ①：主操作「New chat」静止态不可见

截图里 `＋ New chat` 是一行**居中的裸文字**，没有任何按钮外观。原因不是颜色，是 §9.4：

```css
/* guide.css 3305 行，注释原文：「玻璃上不叠卡片，hover 才出现高亮块」 */
.chat-sidebar .sidebar-newchat,
.chat-sidebar .sidebar-action {
    background-color: transparent;
    border-color: transparent;
    box-shadow: none;
}
```

这个决定对**工具栏图标**是对的（避免「玻璃上套卡片」），但对一个页面的**主操作**来说，
静止态零可供性（affordance）——用户第一眼找不到「开始新对话」。

实测：`background-color: rgba(0,0,0,0)`、`border: transparent`、`box-shadow: none`。

### 缺陷 ②：两个 pill 视觉权重完全相同

`New chat` 与 `Training materials` 都是「全透明 + 居中」的同款胶囊，**分不出主次**。

### 缺陷 ③：列表行两行堆叠，时间戳孤立

`.sidebar-item` 是 `flex-direction: column`，标题一行、时间戳一行：

| 实测 | BEFORE |
|---|---|
| 行高 | **47px** |
| 时间戳 | 单独占第二行，11px，`--tx-3` |
| 标题可用宽度 | 192px（但被 2 行高度换来的） |

行高 47px 而侧栏视口 835px → **约 17 行可见**；同屏信息密度低，
且第二行的孤零时间戳让行看起来「没做完」。

### 附带发现（一）：分组标题是 Material 语法

```css
.sidebar-label {
    font-size: 11px;
    text-transform: uppercase;     /* RECENT */
    letter-spacing: 0.08em;
    color: #4a5453;                /* ⚠️ G>R 的 teal 偏色 */
}
```

大写 + 0.08em 字距是 Material / 企业后台的写法，不是 macOS 侧栏的。
且 `#4a5453` 的 G 通道高于 R 通道 —— 是上一轮 teal 主题**没洗干净的残留色相**
（同一个令牌在 `prefers-contrast: more` 下本来就是中性 `#48484a`，说明是遗漏）。

### 附带发现（二）：三个不同的左边界

实测文字落点：

| 元素 | x |
|---|---|
| `.sidebar-newchat` 文字 | **47px** |
| `.sidebar-label` 文字 | **19px** |
| `.sidebar-item-title` 文字 | **21px** |

`Recent` 与列表标题差 2px —— 肉眼能看出「没对齐」。

### 附带发现（三）：中文下按钮高度会跳

i18n 字典里 `"newchat": "＋ 新对话"` —— **全角加号写死在翻译串里**。
一旦给按钮加 SVG 图标，中文界面就会同时出现 SVG 加号 + 全角加号（两个加号）。
另外中文行框比拉丁高，按钮高度 en 34px / zh 37px，切语言会跳 3px。

---

## 2. 改法

| 项目 | BEFORE | AFTER | 依据 |
|---|---|---|---|
| 主操作 New chat | 全透明裸文字，居中 | **Apple 系统蓝实心胶囊** `#0071e3` + 白字，左对齐 图标+文案 | apple.com 按钮蓝；白字 4.70:1 ✅AA |
| 次操作 Training materials | 全透明裸文字，居中 | `rgba(118,118,128,.12)` + 真 hairline，图标用强调色 | Apple `tertiarySystemFill` |
| 分组标题 | `RECENT` 大写 + 0.08em | `Recent` 句首大写，11.5px/600，上方 0.5px 分隔线 | macOS Tahoe 侧栏 |
| 列表行 | 两行堆叠，47px | **单行 30px**：标题弹性 + 时间戳右对齐（等宽数字） | Finder / Mail 列表行 |
| 删除按钮 | 无热区，`×` 直接贴边 | 20×20 圆形热区，hover 圆形底 | Apple 圆形 hover 底 |
| 选中态 | `rgba(0,0,0,0.09)` 中性灰 | **蓝底白字**，标题 600 | 见下方说明 |
| `--tx-3` | `#4a5453`（teal 偏色） | `#545456`（中性，6.9:1） | 对齐 Apple 冷中性 R=G<B |
| 文字基线 | 19 / 21 / 47 三条线 | label 与行标题**同在 21px** | 实测 margin-left 10px |
| 中文加号 | 字典串里带 `＋` | 字典改 `"新对话"`，加号由 SVG 提供 | 否则出现两个加号 |
| 按钮高度 | en 34 / zh 37 | 两种语言**都是 36px** | `line-height: 18px` 锁高 |

**关于选中态用蓝色**：AppKit 里列表选中色是
`NSColor.selectedContentBackgroundColor`，**窗口为 key（活动窗口）时就是强调色**，
窗口非 key 才退成中性灰（`unemphasizedSelectedContentBackgroundColor`）。
网页端恒等于「活动窗口」，所以这里用蓝底白字；hover 仍保持中性灰，层次不丢。

---

## 3. 实测验证

无头 Chrome（`playwright-core` + 系统 Chrome）+ 真实会话数据（`data/ukm_ftsm/conversations/index.json`，
66 条取最近 8 条，经 `GET /api/conversations` 路由注入**真实渲染器** `renderHistoryList()`）：

| 断言 | BEFORE | AFTER |
|---|---|---|
| 玻璃元素数 | 3 | 3（topbar / sidebar / composer） |
| 内容层玻璃违规 | 0 | **0** |
| `.sidebar-item` 行高 | 47px | **30px** |
| `.sidebar-item` 方向 | column | row |
| 选中行背景 | `rgba(0,0,0,0.09)` | **`rgb(0,113,227)`** |
| 选中行标题 | `rgb(29,29,31)` 500 | **`rgb(255,255,255)` 600** |
| New chat 背景 | `rgba(0,0,0,0)` | **`rgb(0,113,227)`** + 白字 |
| Training materials 背景 | `rgba(0,0,0,0)` | `rgba(118,118,128,0.12)` + hairline |
| 分组标题 | 11px / uppercase / 0.88px 字距 / `rgb(74,84,83)` | 11.5px / none / normal / `rgb(110,110,115)` |
| hover 交叉淡变 | — | 时间戳 `opacity 1→0`、`×` `opacity 0→1`，实测 0 / 1 |
| 按钮高度 | en 34 / zh 37 | en 36 / zh 36 |
| 左边界 | 19 / 21 / 47 | label 21 = 标题 21 |
| 页面报错 | 0 | **0** |

CSS 完整性：`guide.css` 3907 行，`{`/`}` 558/558、`/*`/`*/` 169/169；
`liquid-glass-v4.patch.css` 1109 行，141/141、112/112。
旧色相只存活在**说明性注释**里（逐行核对过）。

---

## 4. 取舍与遗留

**取舍一：标题截断缩短了约 4~5 个字符。**
时间戳从第二行搬到同一行，占用 29.1px → 标题可用宽度 192px → 172.9px。
代价是 `How do I renew my stu…` 比原来的 `How do I renew my student …` 短。
但原方案是拿 **17px 行高**换这 5 个字符，而且 8 行里有 4 行标题本来就完全相同
（数据层 `_title_from_first_message` 截到 40 字符，前 25 字符一致），
**截断并没有损害「区分不同对话」的能力**；完整标题仍在原生 `title` tooltip 里。
如果更看重标题宽度，可以把时间戳改成「仅选中行/悬停显示 + 恒定 30px 右槽」，
一行改动即可（把 `.sidebar-item-time` 设为 `display:none`，行 `padding-right` 改 30px）。

**取舍二：`New chat` 用了实心蓝，比「Apple 侧栏一般很安静」更醒目。**
这是刻意的：它原本**完全不可见**，属于从 0 到 1；而且同一页面只有它、分段控件、
以及列表选中项是蓝的，没有再扩散。

**已知遗留（未改，等确认）：**
- 基础层仍有 20 处 `color: #0d0d0d`（近黑）。Apple 的 `label` 是 `#1d1d1f`。
  两者对比度都远超 AA（19:1 / 16.8:1），**肉眼不可分辨**，属于色值洁癖而非缺陷，
  故本轮未做全库清扫。
- `/guide` 仍无暗色模式（`color-scheme: light` 写死），桌面端有。

---

## 5. 产物

| 文件 | 说明 |
|---|---|
| `web/static/guide.css` §11.11 | 本轮全部样式（+213 行，文件末尾） |
| `web/templates/guide.html` | 侧栏标记 + 顶栏 New chat 换 SVG 加号；`guide.css?v=20261016c`、`guide.js?v=20261016b` |
| `web/static/guide.js` | i18n 字典 `newchat` 去掉全角加号 |
| `docs/liquid-glass-v4.patch.css` | 独立可粘贴版同步到 §11.11（1109 行） |
| `docs/sidebar-v5-shots/` | 8 张实测截图（01 前 / 02 后 / 03 悬停 / 04 选中悬停 / 05 顶栏 / 06 整页 / 07 en / 07 zh） |
| `_backup-liquidglass-20261016-sidebar/` | 改前副本（guide.css / guide.html / guide.js） |

> 复现验证：
> `NODE_PATH=~/.workbuddy/binaries/node/workspace/node_modules node /tmp/sidebar-verify.mjs`
> （脚本用 `page.route` 把 `/api/conversations` 换成真实索引数据，
> 页面其余部分仍由服务器真实渲染；BEFORE 分支通过路由回放备份的 HTML+CSS。）
