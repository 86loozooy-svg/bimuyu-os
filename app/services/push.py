"""每日待办推送服务：飞书 / 企业微信 / 钉钉 webhook + 邮件（smtplib）。

配置来自 site_config 表中以 ``notify_`` 为前缀的 key/value。
未配置任何通道时，推送被跳过 —— 此时由站内红点（前端按到期未完成任务计数）兜底提醒。
"""

import smtplib
from datetime import date
from email.mime.text import MIMEText

import requests

# 通知配置默认值（落在 site_config 表中）
NOTIFY_DEFAULTS = {
    "notify_feishu_webhook": "",
    "notify_wecom_webhook": "",
    "notify_dingtalk_webhook": "",
    "notify_email_enabled": "0",
    "notify_email_smtp_host": "",
    "notify_email_smtp_port": "465",
    "notify_email_smtp_user": "",
    "notify_email_smtp_pass": "",
    "notify_email_from": "",
    "notify_email_to": "",
    "notify_push_enabled": "0",
    "notify_push_time": "08:00",
}


def load_notify_config(conn) -> dict:
    """从 site_config 读取通知配置并补齐默认值。"""
    cfg = dict(NOTIFY_DEFAULTS)
    try:
        rows = conn.execute(
            "SELECT key, value FROM site_config WHERE key LIKE 'notify_%'"
        ).fetchall()
        for r in rows:
            cfg[r["key"]] = r["value"]
    except Exception:
        pass
    return cfg


def is_push_enabled(cfg: dict) -> bool:
    return str(cfg.get("notify_push_enabled")) == "1"


def any_channel_configured(cfg: dict) -> bool:
    """只要配置了任一种外部通道即视为可用。"""
    if cfg.get("notify_feishu_webhook"):
        return True
    if cfg.get("notify_wecom_webhook"):
        return True
    if cfg.get("notify_dingtalk_webhook"):
        return True
    if str(cfg.get("notify_email_enabled")) == "1" and cfg.get("notify_email_smtp_host"):
        return True
    return False


def _post_webhook(url: str, text: str, timeout: int = 8) -> bool:
    """飞书/企业微信/钉钉的 text 消息体格式一致，统一推送。"""
    payload = {"msgtype": "text", "text": {"content": text}}
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


def _send_email(text: str, cfg: dict) -> bool:
    host = cfg.get("notify_email_smtp_host")
    user = cfg.get("notify_email_smtp_user")
    to = cfg.get("notify_email_to") or user
    if not (host and user and to):
        return False
    try:
        port = int(cfg.get("notify_email_smtp_port") or 465)
        frm = cfg.get("notify_email_from") or user
        msg = MIMEText(text, "plain", "utf-8")
        msg["Subject"] = "比目鱼（Bimuyu） 每日待办提醒"
        msg["From"] = frm
        msg["To"] = to
        with smtplib.SMTP_SSL(host, port, timeout=10) as server:
            server.login(user, cfg.get("notify_email_smtp_pass") or "")
            server.sendmail(frm, [to], msg.as_string())
        return True
    except Exception:
        return False


def send_push(message: str, cfg: dict) -> dict:
    """按已配置通道推送；返回每个通道的成功与否。"""
    results: dict = {}
    if cfg.get("notify_feishu_webhook"):
        results["feishu"] = _post_webhook(cfg["notify_feishu_webhook"], message)
    if cfg.get("notify_wecom_webhook"):
        results["wecom"] = _post_webhook(cfg["notify_wecom_webhook"], message)
    if cfg.get("notify_dingtalk_webhook"):
        results["dingtalk"] = _post_webhook(cfg["notify_dingtalk_webhook"], message)
    if str(cfg.get("notify_email_enabled")) == "1" and cfg.get("notify_email_smtp_host"):
        results["email"] = _send_email(message, cfg)
    return results


def build_daily_message(tasks: list[dict], today: str) -> str:
    overdue = [t for t in tasks if t.get("due_date") and t["due_date"] < today]
    due_today = [t for t in tasks if t.get("due_date") == today]
    lines = [f"比目鱼（Bimuyu） 每日待办提醒（{today}）", ""]
    if overdue:
        lines.append("⏰ 已逾期：")
        for t in overdue:
            proj = f" #{t['project_id']}" if t.get("project_id") else ""
            lines.append(f"  - [{t.get('priority', 'medium')}] {t['title']}{proj}")
        lines.append("")
    if due_today:
        lines.append("📅 今日到期：")
        for t in due_today:
            proj = f" #{t['project_id']}" if t.get("project_id") else ""
            lines.append(f"  - [{t.get('priority', 'medium')}] {t['title']}{proj}")
    if not overdue and not due_today:
        lines.append("✅ 暂无到期待办")
    return "\n".join(lines)


def scan_and_push() -> dict:
    """扫描到期未完成任务并推送；返回推送摘要。自包含事务。"""
    from app.database import db_session

    today = date.today().isoformat()
    with db_session() as conn:
        cfg = load_notify_config(conn)
        if not is_push_enabled(cfg):
            return {"pushed": 0, "skipped": "disabled"}
        if not any_channel_configured(cfg):
            return {"pushed": 0, "skipped": "no_channel"}
        rows = conn.execute(
            "SELECT * FROM task WHERE status != 'done' AND due_date <= ? "
            "ORDER BY due_date, priority DESC",
            (today,),
        ).fetchall()
        tasks = [dict(r) for r in rows]
        if not tasks:
            return {"pushed": 0, "skipped": "none_due"}
        message = build_daily_message(tasks, today)
        results = send_push(message, cfg)
        ids = [t["id"] for t in tasks]
        placeholders = ",".join("?" * len(ids))
        conn.execute(
            f"UPDATE task SET pushed_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders})",
            ids,
        )
        return {"pushed": len(tasks), "results": results}
