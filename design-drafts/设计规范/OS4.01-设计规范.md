# Studio OS — 设计规范（os 4.01）

> **版本代号**：os 4.01（halo.css v19）
> **状态**：🔒 已冻结（frozen）。任何改动须先经 Jerry 确认。
> **权威实现**：`static/css/halo.css`（== `studio_os_redesign_release/workbench-reference-vision.html` 整页参考的忠实移植）
> **适用范围**：全站（含 dashboard / kanban / projects / quotes / quotations / cost / materials / contacts / members / public / modules / account 等所有视图与二级页面）
> **最后更新**：2026-08-11

---

## 1. 设计原则（铁律）

| 原则 | 说明 |
|---|---|
| 近黑底 + 亮青柠点缀 | 深色为主，单一荧光青柠（`--accent #d8ff3f`）作为唯一强调色 |
| 干净无纹理 | **禁止**颗粒(grain)、毛玻璃(blur)、辉光(glow) 等任何拟物质感 |
| 圆角统一 | 卡片圆角 `--radius: 10px`；按钮圆角 `--radius-btn: 6px` |
| 参考页唯一真值 | 所有视觉严格对齐 `workbench-reference-vision.html`，不擅自发挥 |
| 改动先确认 | 已定稿设计不可回退/擅自改动；想改必须先问 Jerry |

---

## 2. Design Tokens

### 2.1 深色主题（默认，无 `data-theme` 属性即为深色）

| Token | 值 | 用途 |
|---|---|---|
| `--bg` | `#0f0f12` | 页面背景 |
| `--surface` | `#141418` | 侧栏/顶栏/表头等实底 |
| `--card` | `#1a1a1e` | 卡片背景 |
| `--card-hover` | `#1e1e23` | 卡片 hover 背景 |
| `--accent` | `#d8ff3f` | **唯一强调色**（荧光青柠） |
| `--accent-text` | `#0f0f12` | 强调色上的文字（深底） |
| `--accent-hover` | `#c7ee2e` | 强调色 hover |
| `--text-primary` | `#ffffff` | 主文字 |
| `--text-secondary` | `#9ca3af` | 次要文字 |
| `--text-muted` | `#6b7280` | 弱化文字（表头/标签） |
| `--border` | `rgba(255,255,255,0.08)` | 1px 描边 |
| `--radius` | `10px` | 卡片圆角 |
| `--radius-btn` | `6px` | 按钮圆角 |
| `--shadow` | `0 1px 0 rgba(255,255,255,0.04) inset, 0 14px 40px rgba(0,0,0,0.45)` | 卡片阴影 |

**兼容 bridge 别名**（供 app 模板/分享 JS 内联样式使用，均指向上方主 token，**不可反向再引用主 token**）：
`--color-background/--color-surface/--color-elevated/--color-card-hover/--color-primary/--color-primary-hover/--color-primary-ink/--color-text-primary/--color-text-secondary/--color-text-muted/--color-border/--color-border-strong/--color-focus/--radius-sm/--radius-md/--radius-lg(16px)/--shadow-card/--muted`

### 2.2 信号色（功能徽章 / 提示用）

| Token | 值 | 软背景 token |
|---|---|---|
| `--color-success` | `#34d399` | `--color-success-soft: rgba(52,211,153,0.12)` |
| `--color-warning` | `#fbbf24` | `--color-warning-soft: rgba(251,191,36,0.12)` |
| `--color-info` | `#60a5fa` | `--color-info-soft: rgba(96,165,250,0.12)` |
| `--color-error` | `#ef4444` | `--color-error-soft: rgba(239,68,68,0.12)` |
| `--color-primary-soft` | `rgba(216,255,63,0.12)` | 青柠软背景 |

### 2.3 字体 / 间距 / 动效

- 字体：`--font-display / --font-body: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`；`--font-mono: "JetBrains Mono", ui-monospace, monospace`
- 基准字号 `14px`，行高 `1.5`，`-webkit-font-smoothing: antialiased`
- 间距：`--space-3:12px / --space-4:16px / --space-5:20px / --space-6:24px / --space-8:32px`
- 动效：`--motion-base: 140ms`，`--easing-standard: ease`

### 2.4 浅色主题（`[data-theme="light"]`）

| Token | 值 |
|---|---|
| `--bg` | `#f6f6f8` |
| `--surface` | `#ffffff` |
| `--card` | `#ffffff` |
| `--card-hover` | `#f3f4f6` |
| `--accent` | `#9acd32` |
| `--accent-hover` | `#8bbd22` |
| `--text-primary` | `#111111` |
| `--text-secondary` | `#4b5563` |
| `--text-muted` | `#9ca3af` |
| `--border` | `rgba(0,0,0,0.08)` |
| `--shadow` | `0 1px 0 #fff inset, 0 14px 40px rgba(0,0,0,0.08)` |

---

## 3. 组件规范

### 3.1 按钮（对齐参考 `.btn-accent`）

| 类 | 背景 | 文字 | hover | 备注 |
|---|---|---|---|---|
| `.btn-accent` / `.btn-primary` | `var(--accent)` | `var(--accent-text)` | `translateY(-1px)` + 阴影 + `accent-hover` | 主操作；padding `10px 18px`，字 `13px/700`，圆角 `6px` |
| `.btn` / `.btn-secondary` | `rgba(128,128,128,0.12)` | `var(--text-primary)` | 背景 `0.20` | 默认/次操作 |
| `.btn-outline` | 透明 | `var(--accent)` | 边框/字转 `accent-hover` | 1px 青柠边框，padding `9px 14px`，`12px/600` |
| `.btn-sm` | — | — | — | `padding 7px 12px`，`12px` |
| `.btn-danger` | `var(--color-error)` | `#fff` | `#dc2626` + `translateY(-1px)` | 删除等危险操作 |

> ⚠️ **style.css 污染坑**：`base.html` 先加载营销页 `style.css`，其中 `.btn/.btn-primary` 用 `!important` 锁成透明底 + `accent` 字 + `100px` 圆角。halo.css 中对上述按钮的关键属性已加 `!important` 并在其后加载以覆盖。**不可从 base.html 删除 style.css**（诸多模板依赖其 `.card/.form-group/.badge/.tabs` 等类）。

### 3.2 卡片（`.card`）

- 背景 `var(--card)`，圆角 `var(--radius)`，阴影 `var(--shadow)`；hover 背景 `var(--card-hover)`
- 标题：`.card > h3` 或 `.panel h3` —— `15px / 700`，下边距 `16px`
- `.panel`：`padding: 24px`，用于内分区

### 3.3 页头（`.page-header`）

- `display:flex; justify-content:space-between; gap:16px; margin-bottom:24px`（旧 `.app-header` 映射到同规格）
- `.page-title`：`24px / 800`，字距 `-0.02em`，`var(--text-primary)`
- `.page-sub`：`13px`，`var(--text-secondary)`，上边距 `4px`

### 3.4 表格（`.table` / `.card > table` / `table`）

- `font-size:13px`，`border-collapse:collapse`
- `th`：`text-align:left`，`padding 10px 12px`，`var(--text-muted)`，`600`，`1px` 底边
- `td`：`padding 14px 12px`，`var(--text-secondary)`；行 hover 背景 `var(--card-hover)`
- `td strong`：`var(--text-primary) / 600`

### 3.5 标签 / 徽章

- `.tag`：`inline-flex`，`padding 4px 10px`，圆角 `999px`，`11px/700`
  - `.tag-accent`：青柠底 + 深字
  - `.tag-muted`：灰底 + 次字
  - `.tag-risk`：红软底 + `#ef4444`
- `.badge`（pill，同 `.tag` 规格）：默认灰底；`[data-tone="success|warning|info|error"]` 用对应软背景信号色
- `.membership-badge`（权益等级）：带 `::before` 小圆点；`data-level` 取值 `trial(黄)/standard(蓝)/pro(绿)/flagship(青柠)`

### 3.6 指标卡（`.stat-tile` → `.metric`）

- `.stat-tile`：卡片规格；hover `translateY(-2px)`
- `.metric-value`：`32px / 800`，`var(--text-primary)`
- `.metric-label`：`12px`，`var(--text-secondary)`，`600`，大写，`letter-spacing 0.04em`
- `.metric-delta`：`12px`，`var(--accent)`，`700`

### 3.7 网格

- `.grid-3` / `.grid-4`：三/四列栅格；`@media(max-width:1100px)` 降为 2 列；`@media(max-width:720px)` 单列
- `.content`：主内容容器（顶栏自带内距，此容器提供内容内距）

### 3.8 表单 / Select

- 输入/文本域：`padding 10px 12px`，`1px var(--border)`，`--radius-btn` 圆角，`var(--surface)` 底
- focus：边框 `var(--accent)` + `0 0 0 3px rgba(216,255,63,0.12)`
- **Select 统一非原生**：`appearance:none` + 自定义 SVG 箭头（`stroke #6b7280`）+ `padding-right:32px`；并显式覆盖 `.form-group select` 与 `[data-theme="dark"] select` 的高优先级规则

---

## 4. 布局系统

### 4.1 整体框架

- `.app-layout`：`display:flex; min-height:100vh`
- `.app-sidebar`：`width:252px`，`var(--surface)` 实底，`1px` 右边框，`flex-direction:column`
- `.app-main`：`flex:1`，`flex-direction:column`

### 4.2 侧边栏导航（对齐参考页）

- 品牌：实心青柠圆角方块
- 分组标题：小方块 + 中文标题 + 底部贯穿线（**无英文副标**）
- 导航项 `.app-nav a`：compact；图标 `18px` `var(--text-secondary)`；hover 极淡背景 + 字转 `--text-primary`
- 选中态 `.active`：青柠填充（`.dashboard-active` 为 Dashboard 大青柠卡，图标 `20px` 深字）
- 扩展工作台：虚线纯文字项
- 底部：小头像 + 用户名 / 主理人极简标签 + 深色模式自动切换提示（文字左 / 控件右）

### 4.3 顶栏（`.app-topbar`）

- 高 `68px`，`var(--surface)` 实底 + `1px` 描边 + 内距 `32px`
- `.topbar-left / .topbar-right`（gap `12px`）；`.topbar-section` `15px` 次字
- 消息铃铛 `.topbar-bell`：按钮 `18px` 图标；`.topbar-bell__badge` 青柠圆点；面板含头/列表/脚，项 `hover --card-hover`，图标 `32px` 青柠软底

### 4.4 仪表盘 / 工作台

- **旧单列 Dashboard**（`.dashboard`）：`max-width:840px`，含 Hero 卡（`.hero-project` 左侧 `5px` 青柠边 + `96px` `.progress-ring`）、`.stats-grid` 指标、图表、`.project-list/.project-row` 紧凑列表
- **工作台 Bento Grid**（12 栅格，`.bento`，gap `16px`，卡圆角 `10px`）：行1 四指标卡 → 行2 重点项目大卡(8/12) + 日历/时间轴(4/12) → 行3 状态分布(4/12) + 最近动态(4/12) + 快速操作(4/12)；`@media(max-width:980px)` 堆叠单列。样式隔离在 `static/css/cockpit.css`（在 halo.css 之后加载，**halo.css 零改动**）

---

## 5. 图标规范

- 统一 lucide：`base.html` 引本地 `/static/js/lucide.min.js`（已本地化，不依赖 unpkg）
- 全局 `i[data-lucide] / .lucide`：`18px`，`stroke:currentColor`
- 按钮内 `16px`；Dashboard 大卡 `20px`；导航 `18px`

---

## 6. 三点功能样式（参考风格下保留）

| 类前缀 | 功能 |
|---|---|
| `.modal` / `.share-*` | 分享弹窗 |
| `.onb-*` | 新手引导 |
| `.topbar-bell-*` | 消息铃铛 |
| `.membership-badge` | 权益等级 |
| `.import-region` | 批量导入 |

---

## 7. 兼容组件（现有模板沿用，参考风格）

`.stats-grid/.stat-*`（旧指标）、`.chip`（含 `data-tone` 信号色变体）、`.card-header/.card-title`、`.quick-*`、`.grid-2`、`.eyebrow` 等。

---

## 8. 致命坑 / 约束（改动前必读）

1. **`:root` 自引用循环**：切勿把 `--accent-text/--text-*/--radius-*/--shadow/--card` 再反向定义成指向 `--color-*` 别名。已在 `:root` 11–24 行定义为字面量，无需桥接；反向引用会形成循环，使变量"计算时无效"，导致整站文字变黑、圆角变 0、阴影丢失。
2. **style.css 污染**：见 §3.1 说明。靠 halo.css 后加载 + `!important` 覆盖，不可删 style.css。
3. **select 原生外观**：必须 `appearance:none` + 自定义箭头 + 覆盖高优先级规则，否则系统原生下拉破坏风格。
4. **版本号强刷**：改完 `halo.css` 必须升 `?v=`（`base.html` 现引 `halo.css?v=19`），否则浏览器缓存不更新。
5. **改动先确认**：已冻结设计（本规范）任何结构性变更须先问 Jerry，绝不可单方面回退或改回旧版。

---

## 9. 文件与版本清单

- **设计系统唯一实现**：`static/css/halo.css`（v19）
- **工作台新增（隔离）**：`static/css/cockpit.css`（v1，置于 halo.css 之后）
- **导航/页头**：`templates/app/base.html`（`_title_map`：工作台 / Dashboard 一级置顶 + 1px 分割线 + home 图标 + 青柠 2px 左边线）
- **工作台页面**：`templates/app/dashboard.html` + `app/routers/app_dashboard.py`
- **服务**：uvicorn 端口 `8013`，绑 `0.0.0.0`；凭据 `admin@studio.local / admin123`

### 版本演进（概要）

| 代号 | 定位 | 关键事项 |
|---|---|---|
| 3.0 | 基线 | 初版 |
| 3.1–3.4 | 参考 mockup | 对齐参考页视觉 |
| 3.5–3.7 | 部署对齐 | 部署/结构对齐 |
| 3.8 | 全量重铸 | 按参考页重做 |
| 3.9 | 可读/图标 | 阅读优化 + 图标规范 |
| **4.01** | **当前冻结** | **按钮 / select 修复，确立 halo.css 唯一权威** |

> 完整版本登记表见工作区 `.workbuddy/memory/VERSIONS.md`。

---

*本规范由 halo.css 源码核实生成，作为 os 4.01 视觉冻结态的存档真值。*
