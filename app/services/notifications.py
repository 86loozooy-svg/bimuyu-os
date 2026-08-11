"""P3 消息中心：站内通知 CRUD + 触发点。

设计约束：
- 单租户（studio_id 预留列，默认 1），通知全局可见。
- 触发点：项目阶段流转（project_edit）、发票到期（每日 cron）、系统公告（seed/手动）。
- 报价审批 / License 过期：接口就绪，待对应数据源/审批流落地后接入
  （当前 quotes 无采纳端点、License 无持久化过期字段，故为 no-op，不报错）。
"""
from __future__ import annotations

from datetime import date, timedelta

from app.database import db_session, rows_to_list

TYPE_LABELS = {
    "quote_approved": "报价审批",
    "stage_change": "阶段流转",
    "invoice_due": "发票到期",
    "license_expiring": "License 即将过期",
    "announcement": "系统公告",
}


def create_notification(
    type: str, title: str, body: str = "", link: str = "", studio_id: int = 1
) -> int:
    with db_session() as conn:
        cur = conn.execute(
            "INSERT INTO notifications (studio_id, type, title, body, link) VALUES (?,?,?,?,?)",
            (studio_id, type, title, body, link),
        )
        return cur.lastrowid


def list_notifications(limit: int = 30, type_filter: str = None) -> list:
    with db_session() as conn:
        if type_filter:
            rows = rows_to_list(
                conn.execute(
                    "SELECT * FROM notifications WHERE type=? ORDER BY id DESC LIMIT ?",
                    (type_filter, limit),
                ).fetchall()
            )
        else:
            rows = rows_to_list(
                conn.execute(
                    "SELECT * FROM notifications ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
            )
    return rows


def recent(limit: int = 6) -> list:
    return list_notifications(limit=limit)


def unread_count() -> int:
    with db_session() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE is_read=0"
        ).fetchone()[0]


def mark_read(nid: int) -> None:
    with db_session() as conn:
        conn.execute("UPDATE notifications SET is_read=1 WHERE id=?", (nid,))


def mark_all_read() -> None:
    with db_session() as conn:
        conn.execute("UPDATE notifications SET is_read=1")


def prefs() -> dict:
    with db_session() as conn:
        rows = rows_to_list(
            conn.execute("SELECT channel, enabled FROM notification_prefs").fetchall()
        )
    return {r["channel"]: bool(r["enabled"]) for r in rows}


def set_pref(channel: str, enabled: bool) -> None:
    with db_session() as conn:
        conn.execute(
            "UPDATE notification_prefs SET enabled=? WHERE channel=?",
            (1 if enabled else 0, channel),
        )


# ── 触发点 ────────────────────────────────────────────────────────────────
def notify_stage_change(project_id: int, project_code: str, old: str, new: str) -> int:
    return create_notification(
        "stage_change",
        f"项目 {project_code} 阶段更新：{old} → {new}",
        f"项目阶段已从「{old}」流转至「{new}」。",
        f"/app/projects/{project_id}",
    )


def scan_invoice_due(days: int = 7) -> int:
    """cron：扫描未来 days 天内到期且未付的发票，去重创建通知。返回新建数。"""
    today = date.today()
    horizon = today + timedelta(days=days)
    created = 0
    with db_session() as conn:
        rows = rows_to_list(
            conn.execute(
                "SELECT * FROM invoices WHERE paid=0 AND due_date IS NOT NULL "
                "AND due_date BETWEEN ? AND ?",
                (today.isoformat(), horizon.isoformat()),
            ).fetchall()
        )
        for inv in rows:
            link = f"/app/projects/{inv['project_id']}?tab=finance"
            exist = conn.execute(
                "SELECT COUNT(*) FROM notifications WHERE type='invoice_due' "
                "AND link=? AND is_read=0",
                (link,),
            ).fetchone()[0]
            if exist:
                continue
            create_notification(
                "invoice_due",
                f"发票即将到期（{inv['due_date']}）",
                f"项目 {inv['project_id']} 的发票金额 ¥{inv['amount']} 将于 {inv['due_date']} 到期。",
                link,
            )
            created += 1
    return created


def notify_license_expiring() -> int:
    """License 数据源当前未持久化（仅展示字段），无数据可扫描 → no-op。接口就绪。"""
    return 0


def notify_quote_approved(quote_id: int, project_id: int, project_code: str) -> int:
    """报价审批通过触发。当前 quotes 采纳端点未落地，接口就绪，待审批流接入。"""
    return create_notification(
        "quote_approved",
        f"报价单已采纳（项目 {project_code}）",
        f"项目 {project_code} 的报价单 #{quote_id} 已被采纳。",
        f"/app/projects/{project_id}",
    )
