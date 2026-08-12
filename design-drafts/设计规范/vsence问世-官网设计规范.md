# vsence问世 — 官网网页设计规范

> **品牌**：vsence问世（设计工作室经营系统 / 比目鱼（Bimuyu） 对外品牌）
> **适用范围**：对外官网（公开站）`templates/public/*`、`static/css/style.css`、`static/css/case_layout.css`
> **状态**：🔒 已落地使用中（源文件 `style.css` 即权威实现，本规范由其核实整理）
> **最后更新**：2026-08-12

---

## 0. 与内部 app 的关系（重要）

比目鱼（Bimuyu） 有**两套相互独立的设计系统**，不可混用：

| 系统 | 落地文件 | 调性 | 主色 |
|---|---|---|---|
| 内部经营系统（app） | `static/css/halo.css` / `cockpit.css` | 近黑底 + 极简科技 | 荧光青柠 `#d8ff3f`（os 4.01 已冻结） |
| **对外官网（本规范）** | `static/css/style.css` | 暖米色 + 自然质感 + 大图叙事 | 暖灰棕 `#63615A` + 签名绿黄 `#c8ff00` |

> 内部 app 的 `base.html` 仍先引 `style.css`，但靠后加载的 `halo.css` 用 `!important` 覆盖其按钮污染；**两者之间仅共享极少量 token 名称（如 `--bg`），值完全不同**。改动官网时只动 `style.css` 这套，不要触碰 halo 体系。

---

## 1. 设计原则

| 原则 | 说明 |
|---|---|
| 暖中性基底 | 米色/奶油底（`#f7f4ee`），告别冷灰，营造设计工作室的人文质感 |
| 单一结构色 + 签名色 | 暖灰棕 `#63615A` 承担结构/文字链接/描边；**绿黄 `#c8ff00` 仅作 hover/激活填充（签名强调），不作大面积底色** |
| 大图叙事 | Hero/案例/业务板块以全幅图片 + 渐变遮罩驱动，弱化纯文字堆砌 |
| 克制动效 | 圆角胶囊按钮、淡入淡出轮播、`translateY` 微抬升；全局尊重 `prefers-reduced-motion` |
| 圆角偏柔 | 卡片 `14px`、案例卡 `24px`、按钮 `100px`（胶囊） |
| 暗场统一 | Hero / 动态头图 / 移动端 Snap / 页脚走深棕渐变（`#3b332a→#6b5d4f→#2e2823`），与暖色基调同源 |

---

## 2. Design Tokens（`:root` @ style.css）

### 2.1 颜色

| Token | 值 | 用途 |
|---|---|---|
| `--bg` | `#f7f4ee` | 页面背景（暖米色） |
| `--surface` | `#ffffff` | 卡片/表面 |
| `--text` | `#1c201d` | 主文字（近黑暖灰） |
| `--muted` | `#6a645d` | 次要文字 |
| `--accent` | `#63615A` | **结构主色**：导航文字、按钮描边、链接、圆点 |
| `--accent-rgb` | `99, 97, 90` | `--accent` 的 RGB 分量，用于半透明变体 `rgba(var(--accent-rgb), .x)` |
| `--accent-signature` | `#c8ff00` | **签名绿黄**：hover/激活填充（与 `--case-accent` 同值） |
| `--case-accent` | `#c8ff00` | 案例/按钮 hover 统一填充色（绿黄） |
| `--accent-light` | `#ece9e3` | 浅暖底（占位/徽章底） |
| `--border` | `#e3ddd2` | 1px 描边（暖灰） |
| `--radius` | `14px` | 卡片圆角 |
| `--radius-lg` | `24px` | 案例卡大圆角 |
| `--shadow` | `0 10px 30px rgba(99,97,90,0.08)` | 轻投影 |
| `--shadow-card` | `0 8px 24px rgba(0,0,0,.06)` | 卡片投影 |
| `--shadow-card-hover` | `0 12px 30px rgba(26,22,20,.12)` | 卡片 hover 投影 |

> **圆点指示器配色铁律**：默认 `rgba(var(--accent-rgb),.3)` 半透明灰棕；激活 `var(--accent)` 灰棕实心+放大；**全站一律不使用绿色/黄绿色/深绿色圆点**（Hero 深底圆点改用米白派生 `#f5f0e8`，仍不属绿系）。

### 2.2 信号/强调（仅签名色）

| 语义 | 值 |
|---|---|
| 签名强调（hover/激活） | `#c8ff00`（greenyellow） |
| 暗场文字 | `#f7f3ec` / `rgba(245,240,232,.86)` |
| Hero 小标签（移动端暖金） | `#c9a96e`（仍属灰棕家族，非引入新色） |

### 2.3 字体 / 间距 / 动效

- **字体**：
  - `--font / --font-display`：`"Prompt", "Noto Sans SC", "PingFang SC", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`
  - 加载：Google Fonts `Prompt:wght@300;400;500;600;700;800` + `Noto Sans SC:wght@400`（`templates/public/base.html`）
  - 展示字重统一 **300（Light）**；中文正文用 `Noto Sans SC`
- **基准**：`body` 行高 `1.6`；容器 `max-width:1100px`（内容）/ `1200px`（头部），内距 `0 24px` 或 `0 40px`
- **动效**：`--ease-out: cubic-bezier(.23, 1, .32, 1)`；`--lift: -6px`；轮播自动播放 `6s`（hover 暂停、减少动效时关闭）

---

## 3. 排版尺度（Typography）

| 元素 | 规格 |
|---|---|
| Hero 主标题 `.hero-title` | `clamp(2.4rem, 6vw, 4.6rem)` / `300` / 行高 `1.12` / 中文**不加字距** |
| 板块大标题 `.section-title`（能力版图/合作伙伴） | `65px` / `300` / 左对齐；`span`（英文）`display:block` 换行、`65px`、颜色同黑；移动端降 `44px` |
| 通用区块标题 `.section-title` | `clamp(1.6rem, 3.5vw, 2.2rem)` / `300` / 居中 |
| 案例标题 `.case-title h2` | 中文 + `<span>PROJECTS</span>` 换行 |
| Eyebrow 小标签 `.eyebrow` | `Prompt` `13px/500`、`letter-spacing .12–.16em`、大写、`color:var(--accent)`；暗场用 `--accent-light` |
| 业务标题 `.biz-title` | `clamp(2rem, 3.6vw, 3.4rem)` / `300` / 行高 `1.15` |
| 业务描述 `.biz-desc` | `Noto Sans SC` `15px` / 行高 `1.8` / `--muted` / `max-width:480px` |
| 正文/摘要 | `Noto Sans SC` `15–16px` / 行高 `1.7–1.8` |

---

## 4. 组件规范

### 4.1 按钮（统一语言：细描边胶囊 → hover 填充绿黄）

| 类 | 默认 | hover | 备注 |
|---|---|---|---|
| `.btn` / `.btn-primary` | 透明底 + `1px solid var(--accent)` + 字 `var(--accent) !important`、圆角 `100px`、`padding 12px 28px`、`.9rem/500` | 底 `var(--case-accent)` 绿黄、字 `#212121` | 通用主按钮 |
| `.animated-button`（含 `.hero-cta` / `.nav-cta`） | 透明底 + `1px solid var(--accent)` + 字 `var(--accent)`、`100px`、`padding 14px 38px`、`1.05rem/300`；含箭头双 SVG 切换 | 底 `var(--case-accent)` 绿黄、字 `#212121`、箭头由浅色换深色的位移动画 | Hero/导航 CTA |
| `.biz-btn` | 同胶囊描边、`height 65px`、`padding 0 40px`、`14px/300` | 同绿黄填充 | 业务板块 CTA |
| `.case-more` | 文字 `var(--accent)` + `→` 后缀 | hover 字转 `#212121`、箭头右移 | 案例"查看更多" |
| `.btn-pill` | 实底 `var(--accent)`、白字、`100px` | — | 导航内实心按钮 |
| `.contact-btn`（页脚） | `rgba(255,255,255,.12)` 底 + 白字 + `1px` 白边 | `rgba(255,255,255,.2)` | 暗底联系按钮 |

> **铁律**：所有公开站按钮 hover 一律走"描边胶囊 → 填充签名绿黄 `#c8ff00`"这一条语言，不可出现第三种 hover 配色。

### 4.2 顶部导航 `.site-header`

- `position: sticky; top:0; z-index:100`；底 `rgba(255,255,255,.92)` + `backdrop-filter: saturate(180%) blur(10px)` + `1px` 底边；`padding: calc(16px + env(safe-area-inset-top)) 0 16px`
- **三栏布局**：`logo-center`（中）| `nav-left`（左）| `nav-right`（右），`max-width:1200px; padding:0 40px`；桌面用 flex `order` 还原为 左导航 | Logo | 右导航
- 导航链接：`.nav-left a` `Prompt 300` `16px` `--text`；hover `color:var(--accent)` + 1px 下划线 `scaleX` 展开（克制，无缩放/发光）
- Logo：内联 SVG（CSS 描边动画控色 `var(--accent)`），`height 56px`；淡入 `logoFade .8s`
- 移动端（≤768px）：汉堡左上 + Logo 居中（grid `1fr minmax(0,auto) 1fr`）+ 工作台 CTA 右上；滚动后 `.is-scrolled` 由透明转白底

### 4.3 Hero 区 `.hero`

- `.hero-stage`：`height:85vh; min-height:560px; overflow:hidden`
- `.hero-image`：全幅渐变背景（`linear-gradient(135deg,#d4c5b3,#8a9a8e,#4a5568)` 或站点配置），`align-items:flex-end; justify-content:flex-start`（文字锚定左下）
- `.hero-image::after`：双向压暗遮罩（左强右弱 + 底强顶弱），底部向 `--bg` 溶解，消除与下方案例的硬切线
- `.hero-overlay`：文字 `#f7f3ec`、`padding: clamp(28px,6vw,72px)`
- **轮播**：`.hero-track` 内 3 张 `.hero-slide`，自动播放 `6s`、hover 暂停；左右箭头（hover 显示）+ 圆点（在 `.hero-stage` 外部右下角绝对定位，深底用米白 `#f5f0e8`）
- 移动端：全屏沉浸式 `100svh`，头部透明悬浮，滚动阈值后转白底

### 4.4 案例展示 `.case-showcase`

- 左悬浮标题 `.case-title`（`h2` 中文 + `<span>PROJECTS</span>`）+ 右滚动区 `.case-scroll`
- 右侧：`case-grid` 整面网格墙，**JS 匀速上滚 + 滚轮接管**（hover 暂停）；masonry 用 `grid-auto-rows:8px` + `row-gap:16px` 紧密咬合
- `.case-card`：底 `var(--surface)`、圆角 `--radius-lg(24px)`、阴影 `var(--shadow-card)`；hover `translateY(-6px)` + 阴影 + 图片 `scale(1.08)` + 半透明遮罩 `rgba(var(--accent-rgb),.18)` 显隐
- `.case-info`：`h3` `1rem/300`、`.case-more` 箭头后缀

### 4.5 业务板块 `.biz-section`（能力版图）

- 全宽通栏 `background:#fff`、`padding:80px 0`
- `.biz-carousel`：左文字（浅底）+ 右图片非对称分栏（`grid-template-columns:1.05fr 0.95fr`），桌面由 JS 控制 `.active` 显隐
- `.biz-overlay`：左内边距固定 `44px`（与板块标题 `padding-left:44px` 严格对齐，形成统一视觉基准线）
- 3 张 slide（创意视觉 / 空间设计 / 岛式美陈），圆点 + 左右箭头（hover 显示）+ 滚轮翻页；自动 `6s`
- `.biz-eyebrow`：`Prompt 13px/500`、大写、`letter-spacing .16em`、`--accent`；`.biz-btn` 同 §4.1 胶囊语言

### 4.6 合作伙伴 `.clients-section`

- `.container` 解除限宽改为全宽 + `padding:0 40px`，标题左缘与上方通栏对齐
- `.clients-row`：flex 居中、`gap 48px`；`.client-logo` `1.1rem/300`、字距 `.1em`、`#999`、hover `opacity:1`

### 4.7 页脚 `.site-footer`

- 暗底 `#1a1a1a`、字 `#ccc`；`.footer-grid` 4 列 `gap 32px`
- `.footer-col a`：`#b3b3b3`（对比度 ~7.3:1，优于 AA 4.5:1）→ hover `#fff`
- 社交 `.footer-social a`：`36px` 圆、`#333` 底 → hover `var(--accent)`

### 4.8 近期动态 `/news`

- `.news-hero`：深棕渐变 `#3b332a→#6b5d4f→#2e2823`、白字、居中 `padding:88px 0 72px`
- `.news-card`：grid `45% 55%`、底 `1px` 分隔线；hover `translateY(-3px)` + 图片 `scale(1.03)`
- `.news-tag`：实底 `var(--accent)` 白字胶囊；`.news-title` `Noto Sans SC 700 22px`；`.news-more` 箭头位移

### 4.9 圆点指示器（全站唯一定义）

- 容器永远在对应板块**外部正下方**（绝不进 slide/卡片内）
- `.dot`：`8px` 圆、`background:rgba(var(--accent-rgb),.3)`；hover `.6`；`.active` `var(--accent)` + `scale(1.25)`
- Hero 圆点绝对定位到 `.hero` 右下、深底用米白

---

## 5. 响应式

| 断点 | 行为 |
|---|---|
| `≤900px` | 登录页转纵向；Hero 标题降档 |
| `≤768px` | 导航转汉堡 + 三栏 grid；案例网格 `1fr`；业务通栏转横向 snap（`scroll-snap-type:x mandatory`）；板块大标题 `44px`；Hero 全屏沉浸式 `100svh`；页脚 2 列 |
| `≤480px` | 案例网格单列；Logo 高度收敛（26→22→18px）防溢出 |
| 安全区 | 全程 `env(safe-area-inset-*)` 适配刘海/灵动岛/Home Indicator |

---

## 6. 无障碍（A11y）

- 全局 `prefers-reduced-motion: reduce`：关闭轮播自动播放、过渡、位移、缩放、淡入，仅保留颜色/下划线变化（JS 中 `PREFERS_REDUCED_MOTION` 同步停用自动播放与 wheel 翻页）
- 对比度：页脚链接 `#b3b3b3` ~7.3:1；正文 `--text/#1c201d` 对 `--bg/#f7f4ee` 达标
- 焦点：`animated-button:focus-visible` 有 `box-shadow` 描边、`outline:none`
- 语义：轮播/箭头/圆点均带 `aria-label` 与 `aria-current`

---

## 7. 致命坑 / 约束（改动前必读）

1. **按钮污染回调**：`style.css` 的 `.btn/.btn-primary` 用 `!important` 锁成透明底 + `var(--accent)` 字 + `100px` 圆角。内部 app 靠后加载的 `halo.css` 覆盖它；**改官网时这套就是预期行为，不要误删 `!important`**（否则内部 app 按钮会串色）。
2. **签名色不可滥用**：`--case-accent/#c8ff00` 只作 hover/激活填充，禁止做大面积底色或正文色；结构色始终用 `--accent` 暖灰棕。
3. **圆点配色铁律**：全站圆点只用灰棕系（`--accent-rgb` 半透明 / 实心），Hero 深底用米白，**绝不引入绿/黄绿/深绿**。
4. **中文去字距**：所有中文标题/正文 `letter-spacing:normal`（如 `.hero-title`、`.biz-desc`），`0.08em` 会让汉字间出现难看空隙。
5. **轮播结构约束**：圆点容器必须置于板块容器**外部同级**，JS 按 `data-dots`/`data-target` 配对，改动 DOM 结构会破坏联动。
6. **字体加载依赖 CDN**：`Prompt`/`Noto Sans SC` 由 Google Fonts 引入，离线或墙内环境会回退到 `PingFang SC`/系统字体（展示字重 300 可能失真）。
7. **改动先确认**：本规范对应的官网视觉已落地使用，结构性变更须先与 Jerry 确认，不可单方面回退或改回旧版。

---

## 8. 文件清单

- **设计系统唯一实现（官网）**：`static/css/style.css`（含 `:root` token、组件、响应式、A11y）
- **案例布局补充**：`static/css/case_layout.css`（案例卡 `--case-accent` 初定义处，style.css 已冗余镜像以确保未加载时也可用）
- **页面**：`templates/public/index.html`（首页：Hero/案例墙/能力版图/合作伙伴）、`about.html`、`/news`、案例详情/列表、`login.html` 等
- **头部**：`templates/public/base.html`（字体引入、三栏导航骨架、`vsence-theme` 主题键）
- **品牌**：官网域名 `vsence.com`（如 `/pricing` 外链）、联系 `hello@vsence.studio`

---

*本规范由 `static/css/style.css` 及 `templates/public/*` 源码核实整理，作为 vsence问世 对外官网设计语言的存档真值。内部经营系统的设计规范见同目录 `OS4.01-设计规范.md`（两套相互独立，勿混）。*
