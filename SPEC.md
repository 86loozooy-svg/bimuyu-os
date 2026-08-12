# 比目鱼（Bimuyu） — 一人设计工作室 AI 管理工具 SPEC

> 版本：V1.0  
> 适用：一人工装/空间设计工作室（含岛式美陈、品牌零售、餐饮等项目）  
> 目标：一套系统同时承载「对外展示站」+「对内管理后台」，V1 一次出齐

---

## 一、产品定位与总览

比目鱼（Bimuyu） 是一套面向**一人设计工作室**的轻量管理工具，由两个面组成：

| 面 | 路径 | 受众 | 说明 |
|----|------|------|------|
| 对外展示站 | `yourname.com/` | 客户、访客 | 工作室介绍 + 案例展示 + 联系方式 |
| 对内管理后台 | `yourname.com/app` | 你（admin）+ 受邀协作者 | 项目管线、报价、执行、资料库、权限 |

**技术栈（V1）**
- 后端：Python FastAPI
- 前端：Jinja2 模板（后台）+ 纯 HTML/Alpine.js（展示站）
- 数据库：SQLite（V2 可换 Postgres，只改连接串）
- 认证：JWT + 邮箱密码
- 文件存储：本地 `./data/` 目录（V2 可换 NAS/对象存储）
- AI 接入：OpenAI SDK / Codex API（Skill 路由层）

---

## 二、路由总表

### 公开站（无需登录）

| 路由 | 页面 | 数据来源 |
|------|------|---------|
| `/` | 首页（工作室简介 + 精选案例缩略图） | `cases` 表 `is_online=1` |
| `/cases` | 案例列表页（多图卡片） | `cases` 表 |
| `/cases/{slug}` | 案例详情页（大图浏览 + 文字） | `cases` + `case_images` |
| `/about` | 关于我 / 服务范围 | 配置文件或 `pages` 表 |
| 底部联系区（全站共用） | 微信复制 / 小红书跳转 / 抖音跳转 / 电话拨打 | 配置文件 `contact.json` |

### 后台（需登录 + 权限校验）

| 路由 | 页面 |
|------|------|
| `/app/login` | 登录 |
| `/app/` | Dashboard |
| `/app/pipeline` | 线索看板 |
| `/app/projects` | 项目列表 |
| `/app/projects/{id}` | 项目详情（Tabs） |
| `/app/library` | 资料库 |
| `/app/quotes` | 报价中心 |
| `/app/settings` | 设置 |

---

## 三、数据表结构（V1 完整）

### 3.1 用户与权限

```sql
-- 工作室自身档案（仅一条）
CREATE TABLE studio_profile (
  id INTEGER PRIMARY KEY,
  name TEXT,
  logo_path TEXT,
  description TEXT,
  address TEXT,
  tax_id TEXT,
  bank_account TEXT,
  email_signature TEXT,
  default_design_fee_pct REAL DEFAULT 15,
  default_management_fee_pct REAL DEFAULT 8,
  default_tax_pct REAL DEFAULT 6,
  default_margin_pct REAL DEFAULT 25,
  revision_policy TEXT
);

-- 协作者（含 admin 自己）
CREATE TABLE collaborators (
  id INTEGER PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  display_name TEXT,
  role TEXT DEFAULT 'viewer',  -- admin / editor / viewer / installer
  project_ids TEXT DEFAULT '[]',  -- JSON array，admin 为 NULL 表示全部
  invited_by TEXT,
  invited_at DATETIME,
  expires_at DATETIME,
  last_access_at DATETIME,
  revoked BOOLEAN DEFAULT FALSE,
  token TEXT
);

-- 操作日志
CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY,
  actor_id INTEGER,
  action TEXT,
  target_type TEXT,
  target_id INTEGER,
  detail TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 3.2 客户与项目

```sql
CREATE TABLE clients (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  contact_person TEXT,
  phone TEXT,
  email TEXT,
  industry TEXT,  -- 餐饮/零售/美陈/快闪/其他
  notes TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE projects (
  id INTEGER PRIMARY KEY,
  code TEXT UNIQUE,  -- p-2026-001
  name TEXT NOT NULL,
  client_id INTEGER,
  industry TEXT,
  area REAL,  -- 平方米
  status TEXT DEFAULT 'lead',  -- lead/brief/quoting/signed/designing/delivering/done
  start_date DATE,
  deadline DATE,
  budget_min REAL,
  budget_max REAL,
  brief_md TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 项目时间轴/里程碑
CREATE TABLE project_milestones (
  id INTEGER PRIMARY KEY,
  project_id INTEGER,
  name TEXT,
  due_date DATE,
  done BOOLEAN DEFAULT FALSE,
  done_at DATETIME
);

-- 客户反馈日志
CREATE TABLE feedback_log (
  id INTEGER PRIMARY KEY,
  project_id INTEGER,
  raw_input TEXT,  -- 原始微信/邮件内容
  category TEXT,   -- aesthetic/functional/addition/free
  actionable TEXT, -- AI 提取后的结构化建议
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 3.3 报价引擎

```sql
CREATE TABLE materials (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  brand TEXT,
  spec TEXT,
  unit TEXT,
  ref_price REAL,
  supplier TEXT,
  category TEXT,  -- 涂料/木材/金属/亚克力/灯具/其他
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE labor_items (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  unit TEXT,
  day_rate REAL,
  skill_level TEXT  -- 初级/中级/高级/专项
);

CREATE TABLE boq_templates (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,  -- 工装-零售 / 工装-餐饮 / 岛式美陈 / 快闪店
  project_type TEXT,
  json_structure TEXT NOT NULL  -- 分组+子项的 JSON
);

CREATE TABLE quotes (
  id INTEGER PRIMARY KEY,
  project_id INTEGER,
  version INTEGER DEFAULT 1,
  template_id INTEGER,
  json_detail TEXT NOT NULL,  -- 完整 BOQ + 数量 + 单价
  direct_cost REAL,
  design_fee_pct REAL,
  management_fee_pct REAL,
  tax_pct REAL,
  margin_pct REAL,
  total REAL,
  status TEXT DEFAULT 'draft',  -- draft/sent/accepted/rejected
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 3.4 财务

```sql
CREATE TABLE invoices (
  id INTEGER PRIMARY KEY,
  project_id INTEGER,
  type TEXT,  -- 定金/中期/尾款
  amount REAL,
  due_date DATE,
  paid BOOLEAN DEFAULT FALSE,
  paid_at DATETIME,
  invoice_number TEXT
);

CREATE TABLE ledger (
  id INTEGER PRIMARY KEY,
  project_id INTEGER,
  type TEXT,  -- income/expense
  category TEXT,
  amount REAL,
  note TEXT,
  occurred_at DATE
);
```

### 3.5 公开站（独立，不与内部项目绑定）

```sql
-- 案例（手动维护）
CREATE TABLE cases (
  id INTEGER PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,  -- my-cafe-2025
  title TEXT NOT NULL,
  subtitle TEXT,
  description TEXT,  -- 长文描述
  cover_image TEXT,
  sort_order INTEGER DEFAULT 0,
  is_online BOOLEAN DEFAULT FALSE,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 案例图片组
CREATE TABLE case_images (
  id INTEGER PRIMARY KEY,
  case_id INTEGER,
  image_path TEXT,
  caption TEXT,
  sort_order INTEGER DEFAULT 0
);

-- 关于页/服务页内容
CREATE TABLE pages (
  id INTEGER PRIMARY KEY,
  slug TEXT UNIQUE,  -- about / services
  title TEXT,
  body_md TEXT
);

-- 联系方式（公开站底部按钮读取）
-- 存为 JSON 配置文件 contact.json，不进数据库
-- { "wechat": "xxx", "xiaohongshu_url": "...", "douyin_url": "...", "phone": "..." }
```

---

## 四、权限模型

### 角色定义

| 角色 | 可访问 | 不可访问 |
|------|--------|---------|
| `admin`（你） | 全部路由 + 全部项目 + 财务 Tab + 设置 | 无 |
| `editor` | 被授权的项目（Brief/方案/报价/执行/交付） | 财务、其他项目、设置 |
| `viewer` | 被授权的项目（仅只读） | 报价数字、财务、设置 |
| `installer` | 被授权的 1 个项目（仅执行 Tab + 交付确认） | 其余全部 |

### 中间件逻辑（伪代码）

```python
def require_access(project_id=None):
    token = request.headers.get("Authorization")
    user = verify_jwt(token)
    if user.role == "admin":
        return  # 全通
    if project_id:
        allowed = json.loads(user.project_ids or "[]")
        if project_id not in allowed:
            raise HTTPException(403)
    # 路由级：财务/设置 仅 admin
    if request.path.startswith("/app/settings") and user.role != "admin":
        raise HTTPException(403)
    if request.path.startswith("/app/projects/finance") and user.role != "admin":
        raise HTTPException(403)
```

### 邀请流程
1. Admin 在 `/app/settings/collaborators` 输入邮箱 + 角色 + 项目权限 + 有效期
2. 系统生成 token，发邮件含链接 `yourname.com/app/accept-invite?token=xxx`
3. 对方点链接 → 设密码 → 入库 `collaborators`
4. 登录后只能看到被授权的项目
5. Admin 点"撤销" → token 失效 + session 清除 → 立即踢出

---

## 五、页面与功能明细

### 5.1 公开展示站

| 页面 | 功能板块 | 说明 |
|------|---------|------|
| 首页 `/` | Hero 区（工作室一句话定位 + CTA） | 下方精选 3-6 个案例缩略图（按 sort_order） |
| 案例列表 `/cases` | 卡片瀑布流 | 封面 + 标题 + 一句话，点击进详情 |
| 案例详情 `/cases/{slug}` | 大图浏览（左右切换/滚动） + 文字描述 | 多图按 sort_order 排列 |
| 关于 `/about` | 工作室介绍 + 服务范围 | 从 `pages` 表读 |
| 全站底部 | 微信（点击复制） / 小红书（跳转） / 抖音（跳转） / 电话（tel: 拨打） | 从 `contact.json` 读 |

### 5.2 后台 Dashboard `/app/`

| 区块 | 内容 |
|------|------|
| 本周概览 | 进行中项目数 / 本周到期 / 待回款 / 待跟进线索 |
| 项目进度条 | 每个项目当前阶段可视化 |
| 今日待办 | 从 milestones + deadlines 聚合 |
| AI 简报区（V2） | Codex 每日生成文字简报 |

### 5.3 项目详情 Tabs `/app/projects/{id}`

| Tab | 功能 |
|-----|------|
| 概览 | 时间轴、关键指标、最近动态 |
| Brief | Markdown 编辑器 + AI 智能提取（粘贴客户原话→结构化） |
| 方案 | 设计策略草稿区 + 灵感板占位 + 文案区 |
| 报价 | 选 BOQ 模板 → 填量 → 实时计算 → 三档切换 → 导出 PDF |
| 执行 | 任务看板 + 反馈日志 + 变更单 + 预警 |
| 交付 | 交付物清单勾选 + 验收确认 + 归档 |
| 财务 🔒 | 收款计划 + 发票 + 成本核算 + 利润（仅 admin） |
| 协作者 | 成员列表 + 邀请 + 撤销（仅 admin） |

### 5.4 资料库 `/app/library`

| 板块 | 说明 |
|------|------|
| 材料价格表 | CRUD，下拉分类筛选 |
| 人工费表 | CRUD，按工种/技能 |
| BOQ 模板 | 列表 + 选"基于此新建报价" |
| 灵感采集（V2） | URL 粘贴 → 抓图打标 |

### 5.5 报价中心 `/app/quotes`

| 板块 | 说明 |
|------|------|
| 报价列表 | 跨项目所有版本，按状态筛选 |
| 快速新建 | 不进项目直接开报价 |
| 统计（V2） | 中标率、平均利润率图表 |

### 5.6 设置 `/app/settings`（仅 admin）

| 板块 | 说明 |
|------|------|
| 工作室档案 | 名称/logo/地址/税号/银行/签名 |
| 定价基准 | 默认费率%（设计/管理/税/利润） |
| 成员与权限 | 协作者总表 + 邀请 + 撤销 + 操作日志 |
| 公开站管理 | 案例 CRUD + 上下线 + 图片上传 + 关于页编辑 + contact.json 编辑 |
| AI 配置（V2） | AGENTS.md 编辑 + Skill 开关 |

---

## 六、V1 → V2 → V3 切割

### V1（本次要做完）
✅ 公开站：首页 + 案例列表 + 案例详情 + 关于 + 联系按钮  
✅ 后台：登录 + Dashboard + Projects（Brief/报价/执行 三个 Tab）+ Library（材料/人工/BOQ 模板）+ Settings（工作室档案/定价/成员/公开站管理）  
✅ 报价引擎：选模板 → 手填量 → 计算 → 导出 PDF  
✅ 权限：admin + 协作者表 + 项目级白名单 + 撤销  
✅ 案例 CRUD（admin 手动维护）  
✅ 联系方式配置文件  

### V2（迭代）
🔄 Codex 接入：每日简报 / Brief 智能提取 / 反馈分类 / 报价 AI 估量  
🔄 灵感采集（URL 粘贴抓图打标）  
🔄 Pipeline 看板视图  
🔄 报价统计图表 / 中标分析  
🔄 协作者邀请邮件自动化  
🔄 移动端适配  

### V3（补充）
🔄 客户门户（甲方登录看进度）  
🔄 电子签 / 在线支付  
🔄 多工作室租户隔离（SaaS 化）  
🔄 NAS / 对象存储抽象层  
🔄 博客/文章系统（SEO）  

---

## 七、部署方案

### V1：本地开发验证
```
localhost:8000 → 浏览器
SQLite 文件 + ./data/ 文件夹
```

### V2：上云
```
腾讯云轻量服务器（2核2G，≈¥60/月）
+ 域名 yourname.com（≈¥60/年）
+ ICP 备案（个人，1-2 周）
+ Let's Encrypt 免费 HTTPS
```

### 文件存储路径约定
```
./data/
├── db/bimuyu.db
├── public/cases/{case-slug}/   ← 公开案例图
├── private/projects/{code}/    ← 内部项目文件
└── uploads/                    ← 通用上传
```

---

## 八、安全与运维规则

1. 所有密码 bcrypt 哈希，不存明文
2. JWT 存 HttpOnly cookie，不放 URL
3. 文件下载过权限中间件校验，不靠 URL 隐藏
4. 撤销时清 token + 清 session，立即生效
5. 审计日志记录：谁/何时/访问什么/做了什么
6. 定期备份 SQLite（`sqlite3 .backup`）+ 文件目录打包
7. 上传文件类型白名单（图片/PDF），防恶意文件

---

## 九、AGENTS.md（给 AI 开发者的系统提示词）

```markdown
# 比目鱼（Bimuyu） AI 助理规则

## 身份
你是 [工作室名] 设计工作室的运营助理，服务于一人设计工作室主理人。

## 工作室定位
- 业务：工装空间设计、岛式美陈、品牌零售、餐饮空间
- 设计风格：[待主理人填写]
- 服务范围：[待主理人填写]

## 核心规则
1. 任何发给客户的内容（邮件、报价、提案），必须先给主理人看草稿，确认后才算定稿
2. 报价数字永远以主理人最终确认为准，AI 只提供参考区间
3. 不在任何输出里编造未提供的案例或数据
4. 客户反馈整理时，必须区分「审美偏好」「功能性修改」「新增需求」，并标注是否额外收费

## 工作习惯
- 沟通风格：直接、简洁
- 改稿政策：[包含 2 轮修改，超出 ¥xxx/轮]
- 常用工具：[Figma / CAD / SketchUp / Blender]

## 灵感采集规则（V2）
- 指定信源：[待主理人填写]
- 采集频率：每周一 10:00
- 入库格式：inspiration/{日期}-{主题}/
```

---

## 十、交付清单（V1 完成标准）

- [ ] 浏览器开 `localhost:8000` 看到公开站首页 + 案例页可浏览
- [ ] `/app/login` 能登录，Dashboard 显示数据
- [ ] 能新建项目 → 填 Brief → 选 BOQ 模板 → 出报价 PDF
- [ ] 材料表 / 人工表 / BOQ 模板可 CRUD
- [ ] 案例可在后台新建、上传图片、上下线
- [ ] 协作者可邀请、登录后只看到被授权项目
- [ ] 财务 Tab 仅 admin 可见
- [ ] contact.json 的微信/小红书/抖音/电话按钮可用
- [ ] 代码按本 SPEC 结构组织，V2 升级不需重写

---

**SPEC 到此结束。所有后续开发、AI 生成代码、功能取舍，均以本文件为唯一依据。**
