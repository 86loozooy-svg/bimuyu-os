"""Initialize database schema and seed data."""

import json
from datetime import date, datetime, timedelta

from passlib.context import CryptContext

from app.config import (
    BASE_DIR,
    CONTACT_PATH,
    DATA_DIR,
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_PASSWORD,
)
from app.database import db_session, get_connection

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SCHEMA = """
CREATE TABLE IF NOT EXISTS studio_profile (
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

CREATE TABLE IF NOT EXISTS collaborators (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  username TEXT,
  password_hash TEXT NOT NULL,
  display_name TEXT,
  role TEXT DEFAULT 'viewer',
  project_ids TEXT DEFAULT '[]',
  invited_by TEXT,
  invited_at DATETIME,
  expires_at DATETIME,
  last_access_at DATETIME,
  revoked BOOLEAN DEFAULT FALSE,
  token TEXT,
  avatar_url TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor_id INTEGER,
  action TEXT,
  target_type TEXT,
  target_id INTEGER,
  detail TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS clients (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  contact_person TEXT,
  phone TEXT,
  email TEXT,
  industry TEXT,
  notes TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT UNIQUE,
  name TEXT NOT NULL,
  client_id INTEGER,
  industry TEXT,
  area REAL,
  status TEXT DEFAULT 'lead',
  start_date DATE,
  deadline DATE,
  budget_min REAL,
  budget_max REAL,
  brief_md TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (client_id) REFERENCES clients(id)
);

CREATE TABLE IF NOT EXISTS project_milestones (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER,
  name TEXT,
  due_date DATE,
  done BOOLEAN DEFAULT FALSE,
  done_at DATETIME,
  FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS feedback_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER,
  raw_input TEXT,
  category TEXT,
  actionable TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS materials (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  brand TEXT,
  spec TEXT,
  unit TEXT,
  ref_price REAL,
  supplier TEXT,
  category TEXT,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS labor_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  unit TEXT,
  day_rate REAL,
  skill_level TEXT
);

CREATE TABLE IF NOT EXISTS boq_templates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  project_type TEXT,
  json_structure TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quotes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER,
  version INTEGER DEFAULT 1,
  template_id INTEGER,
  json_detail TEXT NOT NULL,
  direct_cost REAL,
  design_fee_pct REAL,
  management_fee_pct REAL,
  tax_pct REAL,
  margin_pct REAL,
  total REAL,
  status TEXT DEFAULT 'draft',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (project_id) REFERENCES projects(id),
  FOREIGN KEY (template_id) REFERENCES boq_templates(id)
);

CREATE TABLE IF NOT EXISTS invoices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER,
  type TEXT,
  amount REAL,
  due_date DATE,
  paid BOOLEAN DEFAULT FALSE,
  paid_at DATETIME,
  invoice_number TEXT,
  FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER,
  type TEXT,
  category TEXT,
  amount REAL,
  note TEXT,
  occurred_at DATE,
  FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS cases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  subtitle TEXT,
  description TEXT,
  cover_image TEXT,
  sort_order INTEGER DEFAULT 0,
  is_online BOOLEAN DEFAULT FALSE,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS case_images (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id INTEGER,
  image_path TEXT,
  caption TEXT,
  sort_order INTEGER DEFAULT 0,
  FOREIGN KEY (case_id) REFERENCES cases(id)
);

CREATE TABLE IF NOT EXISTS pages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT UNIQUE,
  title TEXT,
  body_md TEXT
);

CREATE TABLE IF NOT EXISTS price_catalog (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  unit TEXT DEFAULT '㎡',
  price REAL DEFAULT 0,
  category TEXT DEFAULT '其他',
  note TEXT,
  factor REAL,
  sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS space_presets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  space_type TEXT,
  items_json TEXT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS project_budget_item (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id    INTEGER NOT NULL,
  name          TEXT    NOT NULL,
  category      TEXT,
  planned_amount REAL   NOT NULL DEFAULT 0,
  sort_order    INTEGER DEFAULT 0,
  created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS project_expense (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id     INTEGER NOT NULL,
  budget_item_id INTEGER,
  amount         REAL    NOT NULL,
  payee          TEXT,
  occurred_date  DATE,
  note           TEXT,
  attachment_path TEXT,
  created_by     INTEGER,
  created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS project_material (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id    INTEGER NOT NULL,
  name          TEXT    NOT NULL,
  brand         TEXT,
  spec          TEXT,
  quantity      REAL    DEFAULT 1,
  unit          TEXT,
  unit_price    REAL    DEFAULT 0,
  category      TEXT,
  purchase_stage TEXT,
  status        TEXT    DEFAULT 'pending',
  sort_order    INTEGER DEFAULT 0,
  created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS worker (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  name          TEXT    NOT NULL,
  role          TEXT,
  phone         TEXT,
  wechat        TEXT,
  id_number     TEXT,
  daily_rate    REAL    DEFAULT 0,
  company       TEXT,
  status        TEXT    DEFAULT 'active',
  notes         TEXT,
  created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS project_assignment (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id    INTEGER NOT NULL,
  worker_id     INTEGER NOT NULL,
  role_on_project TEXT,
  is_lead       INTEGER DEFAULT 0,
  start_date    DATE,
  end_date      DATE,
  status        TEXT    DEFAULT 'planned',
  notes         TEXT,
  created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (project_id) REFERENCES projects(id),
  FOREIGN KEY (worker_id) REFERENCES worker(id)
);

CREATE TABLE IF NOT EXISTS task (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id    INTEGER,
  title         TEXT    NOT NULL,
  description   TEXT,
  due_date      DATE,
  due_time      TEXT,
  priority      TEXT    DEFAULT 'medium',
  status        TEXT    DEFAULT 'todo',
  assignee      TEXT,
  source        TEXT    DEFAULT 'manual',
  milestone_id  INTEGER,
  created_by    INTEGER,
  created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
  done_at       DATETIME,
  pushed_at     DATETIME,
  FOREIGN KEY (project_id) REFERENCES projects(id)
);
"""


def init_schema() -> None:
    conn = get_connection()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def _add_columns(conn, table: str, cols: dict) -> None:
    """Add columns if they do not already exist (idempotent, SQLite safe)."""
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, definition in cols.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _migrate_schema() -> None:
    """Idempotent column migrations for databases created before this version.

    Adds designer fields to projects and duration/status fields to
    project_milestones, then backfills existing milestones so the Gantt
    timeline has real data immediately.
    """
    conn = get_connection()
    try:
        _add_columns(
            conn,
            "projects",
            {
                "lead_designer": "TEXT",
                "assistant_designer": "TEXT",
                "construction_lead": "TEXT",
            },
        )
        _add_columns(
            conn,
            "project_milestones",
            {
                "start_date": "DATE",
                "end_date": "DATE",
                "status": "TEXT DEFAULT 'todo'",
            },
        )
        _add_columns(
            conn,
            "collaborators",
            {
                "avatar_url": "TEXT",
                "username": "TEXT",
            },
        )

        # 回灌已有里程碑：补齐 start/end/status，让甘特图立刻可见。
        # 注意：status 列默认值 'todo' 代表「尚未推断」，需按真实状态重算，
        # 不能把它当成已有状态而短路后续判断。
        today = date.today().isoformat()
        rows = conn.execute(
            "SELECT id, project_id, due_date, done, start_date, end_date, status "
            "FROM project_milestones "
            "WHERE start_date IS NULL OR end_date IS NULL OR status IS NULL "
            "OR status = '' OR status = 'todo'"
        ).fetchall()
        for r in rows:
            mid = r["id"]
            pid = r["project_id"]
            due = r["due_date"]
            done = r["done"]
            start = r["start_date"]
            end = r["end_date"]
            st = r["status"]
            proj = conn.execute(
                "SELECT start_date, deadline FROM projects WHERE id = ?", (pid,)
            ).fetchone()
            proj_start = proj["start_date"] if proj else None

            end = end or due or (date.today() + timedelta(days=14)).isoformat()
            # start 为空、或为旧兜底值（等于项目起始日）时，按 end-7d 重算，
            # 避免所有条都从同一天开始。
            if not start or start == proj_start:
                start = (date.fromisoformat(end) - timedelta(days=7)).isoformat()
            # 推断真实状态：'todo' 视为未推断，按 done / 延期 / 未开始 判定
            if st and st != "" and st != "todo":
                status = st
            elif done:
                status = "done"
            elif end < today:
                status = "delayed"
            elif start > today:
                status = "upcoming"
            else:
                status = "active"
            conn.execute(
                "UPDATE project_milestones SET start_date = ?, end_date = ?, status = ? WHERE id = ?",
                (start, end, status, mid),
            )
        conn.commit()
    finally:
        conn.close()


def ensure_cases_columns() -> None:
    """Idempotent: add area / category to cases for the public cascade wall & detail page."""
    conn = get_connection()
    try:
        _add_columns(
            conn,
            "cases",
            {
                "area": "REAL",
                "category": "TEXT",
            },
        )
        conn.commit()
    finally:
        conn.close()


def seed_data() -> None:
    with db_session() as conn:
        if conn.execute("SELECT COUNT(*) FROM studio_profile").fetchone()[0] == 0:
            conn.execute(
                """
                INSERT INTO studio_profile (id, name, description, revision_policy)
                VALUES (1, 'Studio OS 设计工作室',
                        '专注工装空间、岛式美陈、品牌零售与餐饮空间设计。',
                        '包含 2 轮修改，超出按轮收费')
                """
            )

        if conn.execute("SELECT COUNT(*) FROM collaborators").fetchone()[0] == 0:
            conn.execute(
                """
                INSERT INTO collaborators (email, password_hash, display_name, role, project_ids)
                VALUES (?, ?, ?, 'admin', NULL)
                """,
                (
                    DEFAULT_ADMIN_EMAIL,
                    pwd_context.hash(DEFAULT_ADMIN_PASSWORD),
                    "主理人",
                ),
            )

        if conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0] == 0:
            conn.execute(
                """
                INSERT INTO clients (name, contact_person, phone, industry, notes)
                VALUES ('示例餐饮品牌', '张经理', '13900001111', '餐饮', '新店筹备中')
                """
            )

        if conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0:
            conn.execute(
                """
                INSERT INTO projects (code, name, client_id, industry, area, status,
                                      start_date, deadline, budget_min, budget_max, brief_md)
                VALUES ('p-2026-001', '示例咖啡店空间设计', 1, '餐饮', 120,
                        'designing', ?, ?, 150000, 200000, ?)
                """,
                (
                    date.today().isoformat(),
                    (date.today() + timedelta(days=45)).isoformat(),
                    "## 项目背景\n\n客户希望打造一家具有岛屿度假感的精品咖啡店，强调自然材质与开放动线。\n\n## 核心需求\n\n- 座位区约 40 位\n- 吧台 + 外摆区\n- 品牌色：暖木 + 米白",
                ),
            )
            conn.execute(
                """
                INSERT INTO project_milestones (project_id, name, start_date, due_date, end_date, done, status)
                VALUES (1, '方案初稿', ?, ?, ?, 1, 'done'),
                       (1, '施工图', ?, ?, ?, 0, 'active'),
                       (1, '现场交底', ?, ?, ?, 0, 'upcoming')
                """,
                (
                    (date.today() - timedelta(days=21)).isoformat(),
                    (date.today() - timedelta(days=7)).isoformat(),
                    (date.today() - timedelta(days=7)).isoformat(),
                    (date.today() - timedelta(days=7)).isoformat(),
                    (date.today() + timedelta(days=14)).isoformat(),
                    (date.today() + timedelta(days=14)).isoformat(),
                    (date.today() + timedelta(days=14)).isoformat(),
                    (date.today() + timedelta(days=30)).isoformat(),
                    (date.today() + timedelta(days=30)).isoformat(),
                ),
            )

        if conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 0:
            materials = [
                ("乳胶漆", "立邦", "室内墙漆", "㎡", 45, "本地建材", "涂料"),
                ("橡木饰面板", "天然木", "18mm", "㎡", 380, "木作供应商", "木材"),
                ("不锈钢踢脚线", "通用", "80mm", "m", 35, "五金市场", "金属"),
                ("亚克力灯箱", "定制", "3mm", "㎡", 520, "广告制作", "亚克力"),
                ("轨道射灯", "欧普", "7W 3000K", "套", 85, "灯具城", "灯具"),
            ]
            conn.executemany(
                """
                INSERT INTO materials (name, brand, spec, unit, ref_price, supplier, category)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                materials,
            )

        if conn.execute("SELECT COUNT(*) FROM labor_items").fetchone()[0] == 0:
            labor = [
                ("木工", "工日", 450, "中级"),
                ("油漆工", "工日", 380, "中级"),
                ("电工", "工日", 420, "高级"),
                ("安装工", "工日", 350, "初级"),
            ]
            conn.executemany(
                """
                INSERT INTO labor_items (name, unit, day_rate, skill_level)
                VALUES (?, ?, ?, ?)
                """,
                labor,
            )

        if conn.execute("SELECT COUNT(*) FROM boq_templates").fetchone()[0] == 0:
            retail_boq = {
                "groups": [
                    {
                        "name": "基础工程",
                        "items": [
                            {"name": "墙面乳胶漆", "unit": "㎡", "unit_price": 45},
                            {"name": "地面自流平", "unit": "㎡", "unit_price": 65},
                        ],
                    },
                    {
                        "name": "木作工程",
                        "items": [
                            {"name": "橡木饰面板", "unit": "㎡", "unit_price": 380},
                            {"name": "定制柜台", "unit": "m", "unit_price": 1200},
                        ],
                    },
                ]
            }
            cafe_boq = {
                "groups": [
                    {
                        "name": "空间基础",
                        "items": [
                            {"name": "墙面处理", "unit": "㎡", "unit_price": 55},
                            {"name": "地面铺装", "unit": "㎡", "unit_price": 180},
                        ],
                    },
                    {
                        "name": "吧台区",
                        "items": [
                            {"name": "吧台木作", "unit": "m", "unit_price": 1500},
                            {"name": "不锈钢设备台", "unit": "m", "unit_price": 800},
                        ],
                    },
                ]
            }
            conn.execute(
                """
                INSERT INTO boq_templates (name, project_type, json_structure)
                VALUES ('工装-零售', '零售', ?),
                       ('工装-餐饮', '餐饮', ?),
                       ('岛式美陈', '美陈', ?)
                """,
                (
                    json.dumps(retail_boq, ensure_ascii=False),
                    json.dumps(cafe_boq, ensure_ascii=False),
                    json.dumps(retail_boq, ensure_ascii=False),
                ),
            )

        if conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0] == 0:
            conn.execute(
                """
                INSERT INTO cases (slug, title, subtitle, description, cover_image,
                                   sort_order, is_online)
                VALUES ('island-cafe-2025', '岛屿咖啡 · 城市中的度假感',
                        '120㎡ 餐饮空间 · 暖木与自然光',
                        '本项目以「岛屿度假」为概念，通过大面积暖木饰面、弧形吧台与柔和灯光，营造轻松惬意的消费体验。开放动线连接室内与外摆，适合快节奏都市中的慢享时刻。',
                        '/static/img/placeholder-case-1.svg', 1, 1),
                       ('retail-flagship-2024', '品牌旗舰 · 极简零售',
                        '200㎡ 零售空间 · 黑白灰基调',
                        '为新兴生活方式品牌打造的旗舰门店，强调产品陈列的仪式感与空间的流动感。材质以微水泥与金属为主，配合重点照明突出 SKU。',
                        '/static/img/placeholder-case-2.svg', 2, 1),
                       ('popup-island-2024', '岛式美陈 · 快闪装置',
                        '商场中庭 · 15 天快闪',
                        '以岛屿元素为核心的美陈装置，可快速搭建与拆卸。结合品牌色与互动拍照点，活动期间日均引流显著提升。',
                        '/static/img/placeholder-case-3.svg', 3, 1)
                """
            )
            conn.execute(
                """
                INSERT INTO case_images (case_id, image_path, caption, sort_order)
                VALUES (1, '/static/img/placeholder-case-1.svg', '吧台区全景', 1),
                       (1, '/static/img/placeholder-case-2.svg', '座位区细节', 2),
                       (2, '/static/img/placeholder-case-2.svg', '入口立面', 1),
                       (3, '/static/img/placeholder-case-3.svg', '装置鸟瞰', 1)
                """
            )

        if conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0] == 0:
            conn.execute(
                """
                INSERT INTO pages (slug, title, body_md)
                VALUES ('about', '关于我们', ?)
                """,
                (
                    """## 我们是谁

Studio OS 设计工作室由一位独立设计师主理，专注工装空间、岛式美陈、品牌零售与餐饮空间设计。

## 服务范围

- **空间设计**：从概念到施工图的全流程设计
- **美陈装置**：商场快闪、品牌活动、节日主题
- **设计顾问**：品牌升级、门店标准化、设计审核

## 工作方式

直接沟通、快速响应。每个项目配备清晰的时间轴与交付清单，确保从 Brief 到落地的每一步都可追踪。
""",
                ),
            )

        if conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] == 0:
            conn.execute(
                """
                INSERT INTO invoices (project_id, type, amount, due_date, paid)
                VALUES (1, '定金', 50000, ?, 1),
                       (1, '中期', 80000, ?, 0),
                       (1, '尾款', 70000, ?, 0)
                """,
                (
                    date.today().isoformat(),
                    (date.today() + timedelta(days=20)).isoformat(),
                    (date.today() + timedelta(days=45)).isoformat(),
                ),
            )

        if conn.execute("SELECT COUNT(*) FROM price_catalog").fetchone()[0] == 0:
            catalog_items = [
                ("强电改造", "位", 120, "水电", "含线管、电线、人工", None, 1),
                ("弱电改造", "位", 100, "水电", "网线/电视线/电话线点位", None, 2),
                ("水路改造 PPR管", "m", 85, "水电", "冷热水管铺设", None, 3),
                ("下水改造 PVC管", "m", 95, "水电", "排水管改造", None, 4),
                ("开关插座安装", "位", 18, "水电", "不含面板", None, 5),
                ("石膏板平面吊顶", "㎡", 212, "木工", "轻钢龙骨+石膏板", 1.0, 6),
                ("石膏板直线灯池造型跌级吊顶", "m", 208, "木工", "直线灯池/跌级造型", None, 7),
                ("耐水石膏板平面吊顶", "㎡", 264, "木工", "厨房/卫生间适用", 1.0, 8),
                ("欧松板衬底", "㎡", 300, "木工", "基层衬底", None, 9),
                ("木制窗帘盒", "m", 153, "木工", "墙漆饰面", None, 10),
                ("普贴瓷砖 800×800", "㎡", 60, "瓦工", "800×800 普通铺贴", 1.0, 11),
                ("普贴地砖 75×150", "㎡", 168, "瓦工", "750×1500 普通铺贴", 1.0, 12),
                ("薄贴墙砖 60×120", "㎡", 180, "瓦工", "600×1200 薄贴", None, 13),
                ("薄贴墙砖 75×150", "㎡", 220, "瓦工", "750×1500 薄贴", None, 14),
                ("铺贴地砖 600×1200", "㎡", 94, "瓦工", "600×1200 地砖铺贴", 1.0, 15),
                ("墙地面做防水", "㎡", 132, "瓦工", "聚合物水泥防水", None, 16),
                ("地面砂浆干铺垫层", "㎡", 30, "瓦工", "水泥砂浆垫层", 1.0, 17),
                ("墙基层水泥砂浆找平", "㎡", 56, "瓦工", "墙面基层找平", None, 18),
                ("墙基层披刮专用腻子", "㎡", 50, "油工", "环保腻子 2遍", None, 19),
                ("内墙乳胶漆", "㎡", 19, "油工", "一底两面", None, 20),
                ("墙面铲除", "㎡", 18, "油工", "旧墙面铲除", None, 21),
                ("石膏找平", "㎡", 35, "油工", "局部找平修补", None, 22),
                ("过门石安装", "块", 58, "其他", "人工安装", None, 23),
                ("轻体砖围砌管道", "m", 193, "其他", "厨卫包管", None, 24),
                ("厨卫管道降噪防潮", "m", 45, "其他", "隔音棉+防潮处理", None, 25),
                ("瓷砖壁龛砌筑", "项", 800, "其他", "卫生间壁龛", None, 26),
                ("垃圾清运", "项", 800, "其他", "运至小区指定点", None, 27),
                ("成品保护", "项", 500, "其他", "保护膜+胶带", None, 28),
            ]
            conn.executemany(
                """
                INSERT INTO price_catalog (name, unit, price, category, note, factor, sort_order)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                catalog_items,
            )

        if conn.execute("SELECT COUNT(*) FROM space_presets").fetchone()[0] == 0:
            presets = [
                ("客厅", "客厅", json.dumps([
                    {"name": "石膏板平面吊顶", "unit": "㎡", "factor": 1.0, "price": 212, "category": "木工"},
                    {"name": "石膏板直线灯池造型跌级吊顶", "unit": "m", "factor": 0.55, "price": 208, "category": "木工"},
                    {"name": "内墙乳胶漆", "unit": "㎡", "factor": 1.15, "price": 19, "category": "油工"},
                    {"name": "墙基层披刮专用腻子", "unit": "㎡", "factor": 1.25, "price": 50, "category": "油工"},
                    {"name": "地面砂浆干铺垫层", "unit": "㎡", "factor": 1.0, "price": 30, "category": "瓦工"},
                    {"name": "铺贴地砖 600×1200", "unit": "㎡", "factor": 1.0, "price": 94, "category": "瓦工"},
                ], ensure_ascii=False)),
                ("卧室", "卧室", json.dumps([
                    {"name": "石膏板平面吊顶", "unit": "㎡", "factor": 1.0, "price": 212, "category": "木工"},
                    {"name": "内墙乳胶漆", "unit": "㎡", "factor": 2.10, "price": 19, "category": "油工"},
                    {"name": "墙基层披刮专用腻子", "unit": "㎡", "factor": 2.50, "price": 45, "category": "油工"},
                    {"name": "地面砂浆干铺垫层", "unit": "㎡", "factor": 1.0, "price": 30, "category": "瓦工"},
                    {"name": "普贴地砖 75×150", "unit": "㎡", "factor": 1.0, "price": 168, "category": "瓦工"},
                ], ensure_ascii=False)),
                ("厨房", "厨房", json.dumps([
                    {"name": "耐水石膏板平面吊顶", "unit": "㎡", "factor": 1.0, "price": 264, "category": "木工"},
                    {"name": "墙基层水泥砂浆找平", "unit": "㎡", "factor": 2.50, "price": 48, "category": "瓦工"},
                    {"name": "薄贴墙砖 60×120", "unit": "㎡", "factor": 2.80, "price": 180, "category": "瓦工"},
                    {"name": "地面砂浆干铺垫层", "unit": "㎡", "factor": 1.0, "price": 30, "category": "瓦工"},
                    {"name": "铺贴地砖 600×1200", "unit": "㎡", "factor": 1.0, "price": 94, "category": "瓦工"},
                    {"name": "轻体砖围砌管道", "unit": "m", "fixed": 3, "price": 193, "category": "其他"},
                ], ensure_ascii=False)),
                ("卫生间", "卫生间", json.dumps([
                    {"name": "耐水石膏板平面吊顶", "unit": "㎡", "factor": 1.0, "price": 264, "category": "木工"},
                    {"name": "墙基层水泥砂浆找平", "unit": "㎡", "factor": 3.00, "price": 56, "category": "瓦工"},
                    {"name": "薄贴墙砖 60×120", "unit": "㎡", "factor": 5.00, "price": 180, "category": "瓦工"},
                    {"name": "墙地面做防水", "unit": "㎡", "factor": 2.40, "price": 132, "category": "瓦工"},
                    {"name": "地面砂浆干铺垫层", "unit": "㎡", "factor": 1.0, "price": 30, "category": "瓦工"},
                    {"name": "铺贴地砖 600×1200", "unit": "㎡", "factor": 1.0, "price": 94, "category": "瓦工"},
                ], ensure_ascii=False)),
            ]
            for name, space_type, items_json in presets:
                conn.execute(
                    "INSERT INTO space_presets (name, space_type, items_json) VALUES (?, ?, ?)",
                    (name, space_type, items_json),
                )


def ensure_data_dirs() -> None:
    for sub in ("db", "public/cases", "private/projects", "uploads"):
        (DATA_DIR / sub).mkdir(parents=True, exist_ok=True)
    if not CONTACT_PATH.exists():
        CONTACT_PATH.write_text(
            json.dumps(
                {
                    "wechat": "studio_design",
                    "xiaohongshu_url": "https://www.xiaohongshu.com",
                    "douyin_url": "https://www.douyin.com",
                    "phone": "13800000000",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


def main() -> None:
    ensure_data_dirs()
    init_schema()
    _migrate_schema()
    seed_data()
    print("✓ 数据库初始化完成")
    print(f"  路径: {BASE_DIR / 'data' / 'db' / 'studio.db'}")
    print(f"  Admin: {DEFAULT_ADMIN_EMAIL} / {DEFAULT_ADMIN_PASSWORD}")


if __name__ == "__main__":
    main()
