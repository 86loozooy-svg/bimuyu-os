"""项目损益（P&L）派生计算服务。

口径（已与产品确认，P0 冻结）：
- revenue    = 采纳版报价单 total。优先 status='accepted'；无采纳版时取最新非草稿版
              （MVP 过渡，待报价审批流落地后收紧为仅 accepted）。不取 invoices.amount。
- cost       = Σ(project_material.quantity × unit_price)，仅含有效材料行
              （排除标记为 deleted/cancelled 的软删除行；'pending' 计入，代表计划成本）。
- profit     = revenue - cost
- margin_pct = revenue 为 NULL 或 0 时置 NULL；否则 profit / revenue × 100（百分比数值，如 35.0）
- 字段不可由客户端直写，统一由本服务（或定时任务）落库。
"""
from datetime import datetime, date

from app.database import db_session, rows_to_list


def _revenue(conn, pid: int):
    row = conn.execute(
        """
        SELECT total FROM quotes
        WHERE project_id = ? AND status = 'accepted'
        ORDER BY version DESC
        LIMIT 1
        """,
        (pid,),
    ).fetchone()
    if row and row["total"] is not None:
        return float(row["total"])
    # 过渡：无采纳版时取最新非草稿版，便于 MVP 视图非空（审批流落地后收紧）
    row = conn.execute(
        """
        SELECT total FROM quotes
        WHERE project_id = ? AND status IS NOT NULL AND status != 'draft'
        ORDER BY version DESC
        LIMIT 1
        """,
        (pid,),
    ).fetchone()
    if row and row["total"] is not None:
        return float(row["total"])
    return None


def _cost(conn, pid: int) -> float:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(quantity * unit_price), 0)
        FROM project_material
        WHERE project_id = ?
          AND status NOT IN ('deleted', 'cancelled')
        """,
        (pid,),
    ).fetchone()
    return float(row[0]) if row else 0.0


def recalc_project(pid: int) -> dict:
    """重算单个项目的损益派生字段并落库。返回计算结果字典。"""
    with db_session() as conn:
        revenue = _revenue(conn, pid)
        cost = _cost(conn, pid)
        if revenue is None or revenue == 0:
            profit = None
            margin = None
        else:
            profit = round(revenue - cost, 2)
            margin = round(profit / revenue * 100, 2)
        conn.execute(
            """
            UPDATE projects
            SET cost = ?, profit = ?, margin_pct = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (cost, profit, margin, pid),
        )
    return {
        "project_id": pid,
        "revenue": revenue,
        "cost": round(cost, 2),
        "profit": profit,
        "margin_pct": margin,
    }


def recalc_all() -> int:
    """重算所有项目。返回处理项目数。"""
    with db_session() as conn:
        pids = [r[0] for r in conn.execute("SELECT id FROM projects").fetchall()]
    for pid in pids:
        recalc_project(pid)
    return len(pids)


def get_pnl(pid: int) -> dict:
    """读取并计算项目当前损益（不落库，供视图/导出层使用）。"""
    with db_session() as conn:
        revenue = _revenue(conn, pid)
        cost = _cost(conn, pid)
    if revenue is None or revenue == 0:
        profit = None
        margin = None
    else:
        profit = round(revenue - cost, 2)
        margin = round(profit / revenue * 100, 2)
    return {
        "project_id": pid,
        "revenue": revenue,
        "cost": round(cost, 2),
        "profit": profit,
        "margin_pct": margin,
    }


def get_milestone_curve(pid: int) -> list:
    """按里程碑 due_date 分桶，返回累计收入/成本/毛利率曲线（MVP 时间维度近似）。

    成本与收入均无逐里程碑拆分明细，故按里程碑时间轴（due_date 区间长度）
    分摊为累计权重，形成推进过程折线。无有效日期时退化为均匀分摊。
    """
    with db_session() as conn:
        row = conn.execute("SELECT start_date FROM projects WHERE id=?", (pid,)).fetchone()
        start_raw = row["start_date"] if row else None
        ms = rows_to_list(
            conn.execute(
                "SELECT id, name, due_date, done FROM project_milestones "
                "WHERE project_id=? ORDER BY due_date",
                (pid,),
            ).fetchall()
        )
        pnl = get_pnl(pid)
    revenue = pnl["revenue"] or 0.0
    cost = pnl["cost"] or 0.0
    n = len(ms)
    if n == 0:
        return []

    def _parse(d):
        if not d:
            return None
        try:
            return datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
        except Exception:
            return None

    dates = [_parse(m.get("due_date")) for m in ms]
    valid = [d for d in dates if d]
    # 增量权重
    if len(valid) >= 2:
        start = valid[0]
        sp = _parse(start_raw)
        if sp and sp < start:
            start = sp
        span = (valid[-1] - start).days
        if span <= 0:
            inc_w = [1.0 / n] * n
        else:
            cum = [
                ((dates[i] - start).days if dates[i] else 0) / span
                for i in range(n)
            ]
            inc_w = [cum[0]] + [cum[i] - cum[i - 1] for i in range(1, n)]
    else:
        inc_w = [1.0 / n] * n

    out = []
    cum_r = 0.0
    cum_c = 0.0
    for i, m in enumerate(ms):
        cum_r += revenue * inc_w[i]
        cum_c += cost * inc_w[i]
        margin = None if cum_r <= 0 else round((cum_r - cum_c) / cum_r * 100, 2)
        out.append(
            {
                "name": m.get("name") or f"里程碑{i + 1}",
                "date": m.get("due_date"),
                "done": bool(m.get("done")),
                "cum_revenue": round(cum_r, 2),
                "cum_cost": round(cum_c, 2),
                "margin_pct": margin,
            }
        )
    return out
